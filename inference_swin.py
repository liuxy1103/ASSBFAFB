import sys
import torch
import argparse
import numpy as np
import torch.nn as nn
from pathlib import Path
from torch.utils.data import DataLoader
from torch.nn.functional import interpolate
import time
import os
import h5py
from instance_d4_seg_Aug_rotate.predict_sementic import *
from instance_d4_seg_Aug_rotate.Instance_Pipeline import *
from BCE3.predict_anchors import *
from scipy.ndimage.interpolation import zoom
from copy import deepcopy
from util_map.map_eval import eval_mito
# from util_map.metrics import dice_coeff
from skimage.metrics import adapted_rand_error as adapted_rand_ref
from skimage.metrics import variation_of_information as voi_ref


model_state_file = "/trained_model/segmentation_model_swin.pth"
config_path = "./mysetting.yaml"
ckps = 'seed_model_v4.7.pth'

def load_nii(path):
    print(path.split("/")[-1], "loaded!")
    nii = sitk.ReadImage(path)
    nii = sitk.GetArrayFromImage(nii)
    return nii


def save_nii(img,path):
    img = sitk.GetImageFromArray(img)
    sitk.WriteImage(img, path)
    print(path.split("/")[-1], "saving succeed!")


def dice_coeff(pred, target):

    pred = pred>0
    pred = pred.astype(np.uint8)
    target = target>0
    target = target.astype(np.uint8)
    smooth = 0.000001

    m1 = pred.flatten()  # Flatten
    m2 = target.flatten()  # Flatten
    intersection = (m1 * m2).sum()
    intersection = np.float(intersection)

    bing = (np.uint8(m1) | np.uint8(m2)).sum()
    bing = bing.astype('float')
    jac = (intersection + smooth) / (bing + smooth)

    dice = (2. * intersection + smooth) / (m1.sum() + m2.sum() + smooth)

    return dice, jac


if __name__ == "__main__":
    root_path_positive = '/braindat/lab/liuxy/soma_seg/Block_level_experiments/CellBody_raw/TestSet/test_erode'
    # thre_0 = 0.05 # boundary
    # thre_1 = 0.95 # fg
    
    f_all = open('./scores_swin'+'.txt', 'w')
    for i in [0.94]:
        thre_0 = 1-i
        thre_1 = i
        print(i,thre_0)
        out_path = './swin_out'
        if not os.path.exists(out_path):
            os.makedirs(out_path)
        block_list_positive = os.listdir(root_path_positive)
        time_total_list = []
        time_anchor_list=[]
        time_seg_list=[]
        time_instance_list=[]
        arand_list = []
        voi_list = []
        mAP_list = []
        mAP50_list = []
        mAP75_list = []
        dice3d_list = []
        jac3d_list = []
        for block_name in block_list_positive:
            if block_name[-2:]=='_1':
                continue
            block_path = os.path.join(root_path_positive,block_name)
            raw_file = block_name + '_raw.nii.gz'
            raw_stitch = load_nii(os.path.join(block_path,raw_file))
            gt_file = block_name + '_mask.nii.gz'
            gt_seg = load_nii(os.path.join(block_path,gt_file))
            time1 = time.time()
            seed_map = anchors(ckps, raw_stitch) 
            time2 = time.time()
            time_anchor = time2-time1
            time_anchor_list.append(time_anchor)
            seed_map_tmp = deepcopy(seed_map)     
            # save_nii(output.astype(np.uint8)*255,os.path.join(out_path,block_name+'_out_seed.nii.gz'))
            # save_nii(output_tmp.astype(np.float32)*255,os.path.join(out_path,block_name+'_out_seed_tmp.nii.gz'))
            seed_map_up = zoom(seed_map_tmp,zoom=(3, 4, 4), order=0)
            save_nii(seed_map_up.astype(np.uint8),os.path.join(out_path,block_name+'_seed.nii.gz'))
            time3 = time.time()
            sementic_out = main_predict(thre_0,thre_1,config_path=config_path, block=raw_stitch,seed_map = seed_map, model_state_file=model_state_file,if_save_patch=False, block_name=block_name)
            time4 = time.time()
            time_seg = time4 - time3
            time_seg_list.append(time_seg)
            save_nii(sementic_out,os.path.join(out_path,block_name+'_sementic_out.nii.gz'))
            time5 = time.time()
            instance_output = instance(semantic_output=sementic_out)
            time6 = time.time()
            time_instance = time6 - time5
            time_instance_list.append(time_instance)
            save_nii(raw_stitch,os.path.join(out_path,block_name+'_raw.nii.gz'))
            time_total = time_seg +time_anchor+ time_instance
            time_total_list.append(time_total)
            save_nii(instance_output,os.path.join(out_path,block_name+'_instance_output.nii.gz'))
            #evaluate
            arand = adapted_rand_ref(gt_seg, instance_output, ignore_labels=(0))[0]
            arand_list.append(arand)
            voi_split, voi_merge = voi_ref(gt_seg, instance_output, ignore_labels=(0))
            voi_sum = voi_split + voi_merge
            voi_list.append(voi_sum)
            mAP,mAP50,mAP75 = eval_mito(gt_seg, instance_output,'')
            # mAP = 0.0
            mAP_list.append(mAP)
            mAP50_list.append(mAP50)
            mAP75_list.append(mAP75)
            dice3d, jac3d = dice_coeff(instance_output, gt_seg)
            dice3d_list.append(dice3d)
            jac3d_list.append(jac3d)
            f_txt = open(os.path.join(out_path, block_name+'_scores.txt'), 'w')
            f_txt.write('waterz: voi_split=%.6f, voi_merge=%.6f, voi_sum=%.6f, arand=%.6f' % \
            (voi_split, voi_merge, voi_sum, arand))
            f_txt.write('\n')
            f_txt.write('mAP50:%.6f' %mAP50)
            f_txt.write('\n')
            f_txt.write('mAP75:%.6f' %mAP75)
            f_txt.write('\n')
            f_txt.write('time_anchor:%.6f' %time_anchor)
            f_txt.write('\n')
            f_txt.write('time_seg:%.6f' %time_seg)
            f_txt.write('\n')
            f_txt.write('time_instance:%.6f' %time_instance)
            f_txt.write('\n')
            f_txt.write('time_total:%.6f' %time_total)
            f_txt.close()

        print('time_anchor_list:',time_anchor_list)
        print('time_seg_list:',time_seg_list)
        print('time_instance_list:',time_instance_list)
        print('time_total_list:',time_total_list)
        print('arand_list:',arand_list)
        print('voi_list:',voi_list)
        print('mAP_list:',mAP_list)
        print('mAP50_list:',mAP50_list)
        print('mAP75_list:',mAP75_list)
        print('dice3d:',dice3d_list)
        print('jac3d:',jac3d_list)
        f_all = open('./scores_swin'+'.txt', 'a')
        f_all.write('thre_0=%.6f,thre_1=%.6f, voi_sum1=%.6f, arand1=%.6f,dice3d-1=%.6f,jac3d-1=%.6f,mAP-1=%.6f,mAP50-1=%.6f,mAP75-1=%.6f, voi_sum2=%.6f, arand2=%.6f,dice3d-2=%.6f,jac3d-2=%.6f,mAP-2=%.6f,mAP50-2=%.6f,mAP75-2=%.6f' % \
            (thre_0,thre_1,voi_list[0], arand_list[0],dice3d_list[0],jac3d_list[0],mAP_list[0],mAP50_list[0],mAP75_list[0],voi_list[1], arand_list[1],dice3d_list[1],jac3d_list[1],mAP_list[1],mAP50_list[1],mAP75_list[1]))
        f_all = open('./scores_swin'+'.txt', 'a')
        f_all.write('\n')
    f_all.close()
