#!/usr/bin/env python2

# Copyright (C) 2018 Christian Berger
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

# sysv_ipc is needed to access the shared memory where the camera image is present.
import sysv_ipc
# numpy and cv2 are needed to access, modify, or display the pixels
import numpy
import cv2
# OD4Session is needed to send and receive messages
import OD4Session
# Import the OpenDLV Standard Message Set.
import opendlv_standard_message_set_v0_9_6_pb2

################################################################################
# This dictionary contains all distance values to be filled by function onDistance(...).
distances = { "front": 0.0, "left": 0.0, "right": 0.0, "rear": 0.0 };

################################################################################
# This callback is triggered whenever there is a new distance reading coming in.
def onDistance(msg, senderStamp, timeStamps):
    print "Received distance; senderStamp=" + str(senderStamp)
    print "sent: " + str(timeStamps[0]) + ", received: " + str(timeStamps[1]) + ", sample time stamps: " + str(timeStamps[2])
    print msg
    if senderStamp == 0:
        distances["front"] = msg.distance
    if senderStamp == 1:
        distances["left"] = msg.distance
    if senderStamp == 2:
        distances["rear"] = msg.distance
    if senderStamp == 3:
        distances["right"] = msg.distance


# Create a session to send and receive messages from a running OD4Session;
# Replay mode: CID = 253
# Live mode: CID = 112
# TODO: Change to CID 112 when this program is used on Kiwi.
session = OD4Session.OD4Session(cid=253)
# Register a handler for a message; the following example is listening
# for messageID 1039 which represents opendlv.proxy.DistanceReading.
# Cf. here: https://github.com/chalmers-revere/opendlv.standard-message-set/blob/master/opendlv.odvd#L113-L115
messageIDDistanceReading = 1039
session.registerMessageCallback(messageIDDistanceReading, onDistance, opendlv_standard_message_set_v0_9_6_pb2.opendlv_proxy_DistanceReading)
# Connect to the network session.
session.connect()

################################################################################
# The following lines connect to the camera frame that resides in shared memory.
# This name must match with the name used in the h264-decoder-viewer.yml file.
name = "/tmp/img.argb"
# Obtain the keys for the shared memory and semaphores.
keySharedMemory = sysv_ipc.ftok(name, 1, True)
keySemMutex = sysv_ipc.ftok(name, 2, True)
keySemCondition = sysv_ipc.ftok(name, 3, True)
# Instantiate the SharedMemory and Semaphore objects.
shm = sysv_ipc.SharedMemory(keySharedMemory)
mutex = sysv_ipc.Semaphore(keySemCondition)
cond = sysv_ipc.Semaphore(keySemCondition)

################################################################################
# Main loop to process the next image frame coming in.
while True:
    # Wait for next notification.
    cond.Z()
    print "Received new frame."

    # Lock access to shared memory.
    mutex.acquire()
    # Attach to shared memory.
    shm.attach()
    # Read shared memory into own buffer.
    buf = shm.read()
    # Detach to shared memory.
    shm.detach()
    # Unlock access to shared memory.
    mutex.release()

    # Turn buf into img array (640 * 480 * 4 bytes (ARGB)) to be used with OpenCV.
    img = numpy.frombuffer(buf, numpy.uint8).reshape(480, 640, 4)
    
    crop_img = img[0:320, 0:640]
    kernel = numpy.ones((5,5), numpy.uint8)
   
    img = crop_img
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    lower_blue = numpy.array([100,100,30])
    upper_blue = numpy.array([140,255,255])
    
    lower_yellow = numpy.array([20, 100, 100])
    upper_yellow = numpy.array([30, 255, 255])
    
    mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)
    dilated_blue = cv2.dilate(mask_blue, kernel, iterations = 5)
    res_blue = cv2.bitwise_and(img, img, mask= mask_blue)
    
    mask_yellow = cv2.inRange(hsv, lower_yellow, upper_yellow)
    dilated_yellow = cv2.dilate(mask_yellow, kernel, iterations = 5)
    res_yellow = cv2.bitwise_and(img, img, mask= mask_yellow)
    
    edges = cv2.Canny(dilated_blue, 30, 150)
    
    
    lines = cv2.HoughLines(edges,1,numpy.pi/180,25)
    
    
    for rho,theta in lines[0]:
        a = numpy.cos(theta)
        b = numpy.sin(theta)
        x0 = a*rho
        y0 = b*rho
        x1 = int(x0 + 1000*(-b))
        y1 = int(y0 + 1000*(a))
        x2 = int(x0 - 1000*(-b))
        y2 = int(y0 - 1000*(a))
        
        print "x1 = " + str(x1)
        print "x2 = " + str(x2)

        cv2.line(img,(x1,y1),(x2,y2),(0,0,255),2)
    
    
    # TODO: Disable the following lines before running on Kiwi:
    cv2.imshow('Blue cones',dilated_blue)
    cv2.imshow('Yellow cones', dilated_yellow)
    cv2.imshow('Normal img', img)
    cv2.imshow('canny_blue', edges)
    cv2.waitKey(2);

    ############################################################################
    # Example: Accessing the distance readings.
    print "Front = " + str(distances["front"])
    print "Left = " + str(distances["left"])
    print "Right = " + str(distances["right"])
    print "Rear = " + str(distances["rear"])

    ############################################################################
    # Example for creating and sending a message to other microservices; can
    # be removed when not needed.
    angleReading = opendlv_standard_message_set_v0_9_6_pb2.opendlv_proxy_AngleReading()
    angleReading.angle = 123.45

    # 1038 is the message ID for opendlv.proxy.AngleReading
    session.send(1038, angleReading.SerializeToString());

    ############################################################################
    # Steering and acceleration/decelration.
    #
    # Uncomment the following lines to steer; range: +38deg (left) .. -38deg (right).
    # Value groundSteeringRequest.groundSteering must be given in radians (DEG/180. * PI).
    #groundSteeringRequest = opendlv_standard_message_set_v0_9_6_pb2.opendlv_proxy_GroundSteeringRequest()
    #groundSteeringRequest.groundSteering = 0
    #session.send(1090, groundSteeringRequest.SerializeToString());

    # Uncomment the following lines to accelerate/decelerate; range: +0.25 (forward) .. -1.0 (backwards).
    # Be careful!
    #pedalPositionRequest = opendlv_standard_message_set_v0_9_6_pb2.opendlv_proxy_PedalPositionRequest()
    #pedalPositionRequest.position = 0
    #session.send(1086, pedalPositionRequest.SerializeToString());

