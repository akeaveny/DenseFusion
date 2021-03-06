import glob
import numpy as np

import cv2
from PIL import Image
import matplotlib.pyplot as plt

#######################################
#######################################

from tools.Elevator import cfg as config

#######################################
#######################################

def load_obj_ply_files():

    ###################################
    # OG PLY
    ###################################

    class_file = open(config.CLASSES_FILE)
    class_id_file = open(config.CLASS_IDS_FILE)
    class_IDs = np.loadtxt(class_id_file, dtype=np.int32)

    class_IDs = np.array([class_IDs])

    cld = {}
    for class_id in class_IDs:
        class_input = class_file.readline()
        if not class_input:
            break
        input_file = open(config.ROOT_DATA_PATH + 'object_meshes/models/{0}.xyz'.format(class_input))
        cld[class_id] = []
        while 1:
            input_line = input_file.readline()
            if not input_line:
                break
            input_line = input_line[:-1].split(' ')
            cld[class_id].append([float(input_line[0]), float(input_line[1]), float(input_line[2])])
        cld[class_id] = np.array(cld[class_id])
        print("class_id: ", class_id)
        print("class_input: ", class_input.rstrip())
        print("Num Point Clouds: {}\n".format(len(cld[class_id])))
        input_file.close()

    ##################################
    ##################################

    class_file = open(config.CLASSES_FILE)
    obj_classes = np.loadtxt(class_file, dtype=np.str)
    class_id_file = open(config.CLASS_IDS_FILE)
    class_IDs = np.loadtxt(class_id_file, dtype=np.int32)

    class_IDs = np.array([class_IDs])
    obj_classes = np.array([obj_classes])

    return cld, obj_classes, class_IDs