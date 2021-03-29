import torch.utils.data as data
from PIL import Image
import os
import os.path
import torch
import numpy as np
import torchvision.transforms as transforms
import argparse
import time
import random
from lib.transformations import quaternion_from_euler, euler_matrix, random_quaternion, quaternion_matrix
import numpy.ma as ma
import copy
import scipy.misc
import scipy.io as scio
import matplotlib.pyplot as plt
import cv2

#######################################
#######################################

from tools.utils import helper_utils

from tools.Elevator import cfg as config
from tools.Elevator.utils.dataset import elavator_dataset_utils

from tools.Elevator.utils.pose.load_obj_ply_files import load_obj_ply_files

#######################################
#######################################

class PoseDataset(data.Dataset):
    def __init__(self, mode, num_pt, add_noise, root, noise_trans, refine):

        ##################################
        # init path
        ##################################

        if mode == 'train':
            self.path = config.TRAIN_FILE # '/home/akeaveny/catkin_ws/src/object-rpe-ak/DenseFusion/datasets/elevator/dataset_config/data_lists/elevator_train_data_list.txt'
        elif mode == 'test':
            self.path = config.VAL_FILE   # '/home/akeaveny/catkin_ws/src/object-rpe-ak/DenseFusion/datasets/elevator/dataset_config/data_lists/elevator_val_data_list.txt'
        print(self.path)

        self.num_pt = num_pt
        self.root = root
        self.add_noise = add_noise
        self.noise_trans = noise_trans

        ##################################
        # real or syn
        ##################################

        self.list = []
        self.real = []
        # self.syn = []
        input_file = open(self.path)
        while 1:
            input_line = input_file.readline()
            if not input_line:
                break
            if input_line[-1:] == '\n':
                input_line = input_line[:-1]
            self.real.append(input_line)
            # self.syn.append(input_line)
            self.list.append(input_line)
        input_file.close()

        self.length = len(self.list)
        self.len_real = len(self.real)
        # self.len_syn = len(self.syn)

        print("Loaded: ", len(self.list))
        print("Real Images: ", len(self.real))
        # print("SYN Images: ", len(self.syn))

        ##################################
        # IMGAUG
        ##################################

        self.trancolor = transforms.ColorJitter(0.2, 0.2, 0.2, 0.05)
        self.noise_img_loc = 0.0
        self.noise_img_scale = 7.0
        self.minimum_num_pt = 50

        self.norm = transforms.Normalize(mean=[107.1515813/255, 108.32803021/255, 105.53228755/255],
                                          std=[47.80617899/255, 48.83287752/255, 50.25165637/255])

        ##################################
        # 3D models
        ##################################

        self.symmetry_obj_idx = [1]
        self.num_pt_mesh_small = 500
        self.num_pt_mesh_large = 800
        self.refine = refine

        class_file = open(config.CLASSES_FILE)
        class_id_file = open(config.CLASS_IDS_FILE)
        self.class_IDs = np.loadtxt(class_id_file, dtype=np.int32)

        self.cld = {}
        for class_id in self.class_IDs:
            class_input = class_file.readline()
            if not class_input:
                break
            input_file = open(config.ROOT_DATA_PATH + 'models/densefusion/{0}.xyz'.format(class_input[:-1]))
            self.cld[class_id] = []
            while 1:
                input_line = input_file.readline()
                if not input_line:
                    break
                input_line = input_line[:-1].split(' ')
                self.cld[class_id].append([float(input_line[0]), float(input_line[1]), float(input_line[2])])
            self.cld[class_id] = np.array(self.cld[class_id])
            print("class_id: ", class_id)
            print("class_input: ", class_input.rstrip())
            print("Num Point Clouds: {}\n".format(len(self.cld[class_id])))
            input_file.close()

        print("************** LOADED DATASET! **************")

    def __getitem__(self, index):
        # print("index:", index)
        # print("Real:", self.real[index])

        image_addr = self.real[index].rstrip()
        dataset_dir = image_addr.split('rgb/')[0]
        image_num = image_addr.split('rgb/')[-1]

        ##################################
        # init
        ##################################

        img_addr = dataset_dir + 'rgb/' + image_num + config.RGB_EXT
        depth_addr = dataset_dir + 'depth/' + image_num + config.DEPTH_EXT
        label_addr = dataset_dir + 'masks/' + image_num + config.LABEL_EXT
        meta_addr = dataset_dir + 'meta/' + image_num + config.META_EXT

        img = Image.open(img_addr)
        depth = np.array(Image.open(depth_addr))
        label = np.array(Image.open(label_addr))
        meta = scio.loadmat(meta_addr)
        test_folder = '/data/Akeaveny/Datasets/Elevator/test_densefuion/'

        # imgaug
        if self.add_noise:
            img = self.trancolor(img)

        # syn image
        img = np.array(img)
        if img.shape[-1] == 4:
            img = img[..., :3]

        ##################################
        # Affordance IDs
        ##################################

        affordance_ids = np.unique(np.array(label))
        # print("affordance_ids: ", affordance_ids)

        ids = []
        for affordance_id in affordance_ids:
            if affordance_id in self.class_IDs:
                ids.append(affordance_id)

        random_idx = np.random.randint(0, len(ids))
        affordance_id = ids[random_idx]

        ##################################

        idx = affordance_id
        # print("idx: ", idx)
        count = 1000 + idx
        meta_idx = str(count)[1:]

        ##################################
        mask_depth = ma.getmaskarray(ma.masked_not_equal(depth, 0))
        mask_label = ma.getmaskarray(ma.masked_equal(label, idx))
        mask = mask_label * mask_depth

        # while 1:
        #     mask_depth = ma.getmaskarray(ma.masked_not_equal(depth, 0))
        #     mask_label = ma.getmaskarray(ma.masked_equal(label, idx))
        #     mask = mask_label * mask_depth
        #     if len(mask.nonzero()[0]) > self.minimum_num_pt:
        #         break

        ############
        # meta
        ############

        # height = meta['width' + meta_idx].flatten().astype(np.int32)[0]
        # width = meta['height' + meta_idx].flatten().astype(np.int32)[0]
        width = meta['width'].flatten().astype(np.int32)[0]
        height = meta['height'].flatten().astype(np.int32)[0]

        # self.xmap = np.array([[j for i in range(height)] for j in range(width)])
        # self.ymap = np.array([[i for i in range(height)] for j in range(width)])
        self.xmap = np.array([[j for i in range(width)] for j in range(height)])
        self.ymap = np.array([[i for i in range(width)] for j in range(height)])

        cam_cx = meta['cx'][0][0]
        cam_cy = meta['cy'][0][0]
        cam_fx = meta['fx'][0][0]
        cam_fy = meta['fy'][0][0]

        cam_scale = np.array(meta['camera_scale'])[0][0]  # 1000 for depth [mm] to [m]
        border_list = np.array(meta['border']).flatten().astype(np.int32)

        ####################
        ####################
        obj_meta_idx = str(1000 + affordance_id)[1:]
        obj_bbox = np.array(meta['obj_bbox_' + np.str(obj_meta_idx)]).flatten()

        # cv2.rectangle(img_bbox, (x1, y1), (x2, y2), (255, 0, 0), 2)
        # cv2_gt_pose = cv2.rectangle(cv2_gt_pose, (cmin, rmin), (cmax, rmax), obj_color, 2)
        # rmin, rmax, cmin, cmax
        x1, y1, x2, y2 = obj_bbox[0], obj_bbox[1], obj_bbox[2], obj_bbox[3]
        rmin, rmax, cmin, cmax = y1, y2, x1, x2
        # print("rmin, rmax, cmin, cmax: ", rmin, rmax, cmin, cmax)

        cam_rotation4 = meta['obj_rotation_' + np.str(obj_meta_idx)]
        cam_translation = meta['obj_translation_' + np.str(obj_meta_idx)] # in [m]

        ############

        img = np.transpose(np.array(img)[:, :, :3], (2, 0, 1))[:, rmin:rmax, cmin:cmax]
        img_masked = np.array(img)

        choose = mask[rmin:rmax, cmin:cmax].flatten().nonzero()[0]

        # print("choose: ", self.num_pt - len(choose))
        if len(choose) == 0:
            print("\n*** CHOOSE IS ZERO ***")
            print('{0}/{1}_rgb.png'.format(self.root, self.list[index]))
            exit(1)

        if len(choose) > self.num_pt:
            c_mask = np.zeros(len(choose), dtype=int)
            c_mask[:self.num_pt] = 1
            np.random.shuffle(c_mask)
            choose = choose[c_mask.nonzero()]
        else:
            choose = np.pad(choose, (0, self.num_pt - len(choose)), 'wrap')

        depth_masked = depth[rmin:rmax, cmin:cmax].flatten()[choose][:, np.newaxis].astype(np.float32)
        xmap_masked = self.xmap[rmin:rmax, cmin:cmax].flatten()[choose][:, np.newaxis].astype(np.float32)
        ymap_masked = self.ymap[rmin:rmax, cmin:cmax].flatten()[choose][:, np.newaxis].astype(np.float32)
        choose = np.array([choose])

        ############
        # cld
        ############

        pt2 = depth_masked / cam_scale
        pt0 = (ymap_masked - cam_cx) * pt2 / cam_fx
        pt1 = (xmap_masked - cam_cy) * pt2 / cam_fy
        cloud = np.concatenate((pt0, pt1, pt2), axis=1)

        translation_noise = np.array([random.uniform(-self.noise_trans, self.noise_trans) for i in range(3)])
        if self.add_noise:
            cloud = np.add(cloud, translation_noise)

        dellist = [j for j in range(0, len(self.cld[idx]))]
        if self.refine:
            dellist = random.sample(dellist, len(self.cld[idx]) - self.num_pt_mesh_large)
        else:
            dellist = random.sample(dellist, len(self.cld[idx]) - self.num_pt_mesh_small)
        model_points = np.delete(self.cld[idx], dellist, axis=0)

        target = np.dot(model_points, cam_rotation4.T)
        if self.add_noise:
            target = np.add(target, cam_translation + translation_noise)
        else:
            target = np.add(target, cam_translation)

        # ######################################
        # ### PROJECT TO SCREEN
        # ######################################
        #
        # cam_mat = np.array([[cam_fx, 0, cam_cx], [0, cam_fy, cam_cy], [0, 0, 1]])
        # dist = np.array([0.0, 0.0, 0.0, 0.0, 0.0])
        #
        # # cv2_img = Image.open('{0}/{1}_rgb.png'.format(self.root, self.list[index]))
        # cv2_img = Image.open(img_addr)
        # imgpts, jac = cv2.projectPoints(cloud, np.eye(3), np.zeros(shape=cam_translation.shape), cam_mat, dist)
        # cv2_img = cv2.polylines(np.array(cv2_img), np.int32([np.squeeze(imgpts)]), True, (0, 255, 255))
        # temp_folder = test_folder + 'cv2.cloud.png'
        # cv2.imwrite(temp_folder, cv2_img)
        #
        # # cv2_img = Image.open('{0}/{1}_rgb.png'.format(self.root, self.list[index]))
        # cv2_img = Image.open(img_addr)
        # imgpts, jac = cv2.projectPoints(target, np.eye(3), np.zeros(shape=cam_translation.shape), cam_mat, dist)
        # cv2_img = cv2.polylines(np.array(cv2_img), np.int32([np.squeeze(imgpts)]), True, (0, 255, 255))
        # temp_folder = test_folder + 'cv2.target.png'
        # cv2.imwrite(temp_folder, cv2_img)
        #
        # # cv2_img = Image.open('{0}/{1}_rgb.png'.format(self.root, self.list[index]))
        # cv2_img = Image.open(img_addr)
        # imgpts, jac = cv2.projectPoints(model_points * 1e3, cam_rotation4, cam_translation*1e3, cam_mat, dist)
        # cv2_img = cv2.polylines(np.array(cv2_img), np.int32([np.squeeze(imgpts)]), True, (0, 255, 255))
        # temp_folder = test_folder + 'cv2.model_points.png'
        # cv2.imwrite(temp_folder, cv2_img)
        #
        # # cv2_img = Image.open('{0}/{1}_rgb.png'.format(self.root, self.list[index]))
        # cv2_img = Image.open(img_addr)
        # imgpts, jac = cv2.projectPoints(self.cld[idx] * 1e3, cam_rotation4, cam_translation*1e3, cam_mat, dist)
        # cv2_img = cv2.polylines(np.array(cv2_img), np.int32([np.squeeze(imgpts)]), True, (0, 255, 255))
        # temp_folder = test_folder + 'cv2.1.gt.png'
        # cv2.imwrite(temp_folder, cv2_img)
        #
        # # cv2_img = Image.open('{0}/{1}_rgb.png'.format(self.root, self.list[index]))
        # cv2_img = Image.open(img_addr)
        # imgpts, jac = cv2.projectPoints(self.cld[idx] * 1e3, cam_rotation4, cam_translation*1e3, cam_mat, dist)
        # cv2_img = cv2.polylines(np.array(cv2_img), np.int32([np.squeeze(imgpts)]), True, (0, 255, 255))
        # temp_folder = test_folder + 'cv2.1.gt.png'
        # cv2.imwrite(temp_folder, cv2_img)
        #
        # ######################################
        # ### SAVE IMAGES
        # ######################################
        #
        # # img = Image.open('{0}/{1}_rgb.png'.format(self.root, self.list[index]))
        # img = Image.open(img_addr)
        #
        # ### display bbox
        # img_bbox = np.array(img.copy())
        # img_name = test_folder + '1.bbox.png'
        # cv2.rectangle(img_bbox, (cmin, rmin), (cmax, rmax), (255, 0, 0), 2)
        # cv2.imwrite(img_name, img_bbox)
        #
        # p_img = np.transpose(img_masked, (1, 2, 0))
        # temp_folder = test_folder + '1.input.png'
        # scipy.misc.imsave(temp_folder, p_img)
        # temp_folder = test_folder + '1.label.png'
        # scipy.misc.imsave(temp_folder, mask[rmin:rmax, cmin:cmax].astype(np.int32))

        return torch.from_numpy(cloud.astype(np.float32)), \
               torch.LongTensor(choose.astype(np.int32)), \
               self.norm(torch.from_numpy(img_masked.astype(np.float32))), \
               torch.from_numpy(target.astype(np.float32)), \
               torch.from_numpy(model_points.astype(np.float32)), \
               torch.LongTensor([int(idx) - 1])

    def __len__(self):
        return self.length

    def get_sym_list(self):
        return self.symmetry_obj_idx

    def get_num_points_mesh(self):
        if self.refine:
            return self.num_pt_mesh_large
        else:
            return self.num_pt_mesh_small

def get_bbox(label, affordance_id, img_width, img_length, border_list):


    ###################
    # affordance id
    ###################

    rows = np.any(label==affordance_id, axis=1)
    cols = np.any(label==affordance_id, axis=0)
    ### rows = np.any(label, axis=1)
    ### cols = np.any(label, axis=0)

    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    rmax += 1
    cmax += 1
    r_b = rmax - rmin
    for tt in range(len(border_list)):
        if r_b > border_list[tt] and r_b < border_list[tt + 1]:
            r_b = border_list[tt + 1]
            break
    c_b = cmax - cmin
    for tt in range(len(border_list)):
        if c_b > border_list[tt] and c_b < border_list[tt + 1]:
            c_b = border_list[tt + 1]
            break
    center = [int((rmin + rmax) / 2), int((cmin + cmax) / 2)]
    rmin = center[0] - int(r_b / 2)
    rmax = center[0] + int(r_b / 2)
    cmin = center[1] - int(c_b / 2)
    cmax = center[1] + int(c_b / 2)
    if rmin < 0:
        delt = -rmin
        rmin = 0
        rmax += delt
    if cmin < 0:
        delt = -cmin
        cmin = 0
        cmax += delt
    if rmax > img_width:
        delt = rmax - img_width
        rmax = img_width
        rmin -= delt
    if cmax > img_length:
        delt = cmax - img_length
        cmax = img_length
        cmin -= delt
        # x1,y1 ------
        # |          |
        # |          |
        # |          |
        # --------x2,y2
        # cv2.rectangle(img_bbox, (x1, y1), (x2, y2), (255, 0, 0), 2)
    return rmin, rmax, cmin, cmax