#!/usr/bin/env python

import time
import cv2

if __name__ == '__main__' :

    # Start default camera
    video = cv2.VideoCapture("test.MOV");

    # Find OpenCV version
    (major_ver, minor_ver, subminor_ver) = (cv2.__version__).split('.')

    # With webcam get(CV_CAP_PROP_FPS) does not work.
    # Let's see for ourselves.

    if int(major_ver)  < 3 :
        fps = video.get(cv2.cv.CV_CAP_PROP_FPS)
        print(f"Frames per second using video.get(cv2.cv.CV_CAP_PROP_FPS): {fps}")
    else :
        fps = video.get(cv2.CAP_PROP_FPS)
        print(f"Frames per second using video.get(cv2.CAP_PROP_FPS) : {fps}")

    print(fps)

    count = 0
    start = time.time()
    while video.isOpened():
        ret, frame = video.read()
        if ret:
            count += 1
        else:
            break
    
    end = time.time()
    elapsed = end - start
    # Release video
    video.release()

    print(f"Total number of frame: {count}, elapsed time: {elapsed}")
    print(f"fps: {count//elapsed}")