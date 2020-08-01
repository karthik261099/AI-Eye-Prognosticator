from absl import flags
import sys
FLAGS = flags.FLAGS
FLAGS(sys.argv)

import time
import numpy as np
import cv2
import matplotlib.pyplot as plt

import tensorflow as tf
from yolov3_tf2.models import YoloV3
from yolov3_tf2.dataset import transform_images
from yolov3_tf2.utils import convert_boxes

from deep_sort import preprocessing
from deep_sort import nn_matching
from deep_sort.detection import Detection
from deep_sort.tracker import Tracker
from tools import generate_detections as gdet

####CUSTOM PARAMETERS############################################################
objectsToTrack=["person","car"]


lineOrientationHorizontal=True
#0.5 Means line will be on middle of video vertically, small is closer to top
bandMidLineWrtHeightOrWidth=0.5
#upperBound is height*upDownBoundWrtMidLine above mid line, similarly, lowerbound. Bigger the number, bigger is the area
upDownBoundWrtMidLine=0.05


inputVideo='./inputs/video3.mp4'
# inputVideo='http://192.168.0.25:8080/video'#IP WebCam App
# inputVideo=0

outputVideoName='output'

#############################################################CUSTOM PARAMETERS###


class_names = [c.strip() for c in open('./data/labels/coco.names').readlines()]
yolo = YoloV3(classes=len(class_names))
yolo.load_weights('./weights/yolov3.tf')

max_cosine_distance = 0.5
nn_budget = None
nms_max_overlap = 0.8

model_filename = 'model_data/mars-small128.pb'
encoder = gdet.create_box_encoder(model_filename, batch_size=1)
metric = nn_matching.NearestNeighborDistanceMetric('cosine', max_cosine_distance, nn_budget)
tracker = Tracker(metric)

vid = cv2.VideoCapture(inputVideo)

codec = cv2.VideoWriter_fourcc(*'XVID')
vid_fps =int(vid.get(cv2.CAP_PROP_FPS))
vid_width,vid_height = int(vid.get(cv2.CAP_PROP_FRAME_WIDTH)), int(vid.get(cv2.CAP_PROP_FRAME_HEIGHT))
out = cv2.VideoWriter('./data/video/'+outputVideoName+'.avi', codec, vid_fps, (vid_width, vid_height))

from _collections import deque
pts = [deque(maxlen=30) for _ in range(1000)]

counter = []
for i in objectsToTrack:
    counter.append([-1])#FOR EACH OBJECT LIKE  PERSON OR CAR, A TOTAL COUNTER IS CREATED

while True:
    _, img = vid.read()
    if img is None:
        print('Completed')
        break

    img_in = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img_in = tf.expand_dims(img_in, 0)
    img_in = transform_images(img_in, 416)

    t1 = time.time()

    boxes, scores, classes, nums = yolo.predict(img_in)

    classes = classes[0]
    names = []
    for i in range(len(classes)):
        names.append(class_names[int(classes[i])])
    names = np.array(names)
    converted_boxes = convert_boxes(img, boxes[0])
    features = encoder(img, converted_boxes)

    detections = [Detection(bbox, score, class_name, feature) for bbox, score, class_name, feature in
                  zip(converted_boxes, scores[0], names, features)]

    boxs = np.array([d.tlwh for d in detections])
    scores = np.array([d.confidence for d in detections])
    classes = np.array([d.class_name for d in detections])
    indices = preprocessing.non_max_suppression(boxs, classes, nms_max_overlap, scores)
    detections = [detections[i] for i in indices]

    tracker.predict()
    tracker.update(detections)

    cmap = plt.get_cmap('tab20b')
    colors = [cmap(i)[:3] for i in np.linspace(0,1,20)]

    current_count = [0]*len(objectsToTrack)#FOR EACH OBJECT LIKE  PERSON OR CAR, A CURRENT(Band) COUNTER IS CREATED

    for track in tracker.tracks:
        if not track.is_confirmed() or track.time_since_update >1:
            continue
        bbox = track.to_tlbr()
        class_name= track.get_class()
        color = colors[int(track.track_id) % len(colors)]
        color = [i * 255 for i in color]

        cv2.rectangle(img, (int(bbox[0]),int(bbox[1])), (int(bbox[2]),int(bbox[3])), color, 2)
        cv2.rectangle(img, (int(bbox[0]), int(bbox[1]-30)), (int(bbox[0])+(len(class_name)
                    +len(str(track.track_id)))*13, int(bbox[1])), color, -1)
        cv2.putText(img, class_name+"-"+str(track.track_id), (int(bbox[0]), int(bbox[1]-10)), 0, 0.5,
                    (255, 255, 255), 1)

        center = (int(((bbox[0]) + (bbox[2]))/2), int(((bbox[1])+(bbox[3]))/2))
        pts[track.track_id].append(center)

        for j in range(1, len(pts[track.track_id])):
            if pts[track.track_id][j-1] is None or pts[track.track_id][j] is None:
                continue
            thickness = int(np.sqrt(64/float(j+1))*2)
            cv2.line(img, (pts[track.track_id][j-1]), (pts[track.track_id][j]), color, thickness)


        center_y = int(((bbox[1]) + (bbox[3]))/2) 
        center_x = int(((bbox[0]) + (bbox[2]))/2)

        height, width, _ = img.shape

        if lineOrientationHorizontal:
            #CREATE HORIZONTAL LINES (Zone or band)
            cv2.line(img, (0, int(bandMidLineWrtHeightOrWidth*height+upDownBoundWrtMidLine*height)), (width, int(bandMidLineWrtHeightOrWidth*height+upDownBoundWrtMidLine*height)), (0, 255, 0), thickness=2)
            cv2.line(img, (0, int(bandMidLineWrtHeightOrWidth*height-upDownBoundWrtMidLine*height)), (width, int(bandMidLineWrtHeightOrWidth*height-upDownBoundWrtMidLine*height)), (0, 255, 0), thickness=2)

            if center_y <= int(bandMidLineWrtHeightOrWidth*height+upDownBoundWrtMidLine*height) and center_y >= int(bandMidLineWrtHeightOrWidth*height-upDownBoundWrtMidLine*height):
                if class_name in objectsToTrack:
                    index=objectsToTrack.index(class_name)
                    current_count[index] += 1
                    counter[index].append(int(track.track_id))
        else:
            #CREATE VERTICAL LINES (Zone or band)
            cv2.line(img, (int(bandMidLineWrtHeightOrWidth*width+upDownBoundWrtMidLine*width), 0), (int(bandMidLineWrtHeightOrWidth*width+upDownBoundWrtMidLine*width), height), (0, 255, 0), thickness=2)
            cv2.line(img, (int(bandMidLineWrtHeightOrWidth*width-upDownBoundWrtMidLine*width), 0), (int(bandMidLineWrtHeightOrWidth*width-upDownBoundWrtMidLine*width), height), (0, 255, 0), thickness=2)

            if center_x <= int(bandMidLineWrtHeightOrWidth*width+upDownBoundWrtMidLine*width) and center_x >= int(bandMidLineWrtHeightOrWidth*width-upDownBoundWrtMidLine*width):
                if class_name in objectsToTrack:
                    index=objectsToTrack.index(class_name)
                    current_count[index] += 1
                    counter[index].append(int(track.track_id))


    initialHeight=60
    for objectName in objectsToTrack:
        index=objectsToTrack.index(objectName)
        cv2.putText(img, "Band "+objectName+" count: " + str(current_count[index]), (10, initialHeight), 0, 0.8, (0, 0, 255), 2)
        initialHeight+=30
        total_count = len(set(counter[index]))-1
        cv2.putText(img, "Total "+objectName+" count: " + str(total_count), (10,initialHeight), 0, 0.8, (0,0,255), 2)
        initialHeight+=30

    fps = 1./(time.time()-t1)
    cv2.putText(img, "FPS: {:.2f}".format(fps), (10,30), 0, 0.8, (0,0,255), 2)
    cv2.resizeWindow(outputVideoName, 1024, 768)
    cv2.imshow(outputVideoName, img)
    out.write(img)

    if cv2.waitKey(1) == ord('q'):
        break

vid.release()
out.release()
cv2.destroyAllWindows()