#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
@author: lavanya
Generate constraint maps from relevant MR contrast space
This is an offline step that must be run to generate constraint maps once a relevant multi-contrast space
has been identified for training with the MR-contrast guided contrastive learning approach
"""

import os, natsort 
import scipy.io as sio
import pathlib
from sklearn.cluster import MiniBatchKMeans
import sys, numpy as np
import nibabel as nib
from sklearn.decomposition import PCA
import argparse
import numpy as np

sys.path.append('/content/drive/Othercomputers/My Mac/Documents/GitHub/multi-contrast-contrastive-learning/')
  
from utils.utils import myCrop3D
from utils.utils import  performDenoising
from utils.utils import contrastStretch, normalize_img
 
def main():
    description_txt = 'Constraint map generation for CCL'
    parser = argparse.ArgumentParser(description=description_txt)
    parser.add_argument("--save_dir", type=str, default=None,
                    help="/output/file/location/for/Constraint_maps/")
    parser.add_argument("--data_dir", type=str, default=None,
                    help="/input/nitfi/data/location/here")
    parser.add_argument("--opShape", type=int, default=160,
                    help="Matrix size X (Int)(Default 160)" )
    parser.add_argument("--numCluster", type=int, default=20,
                    help="NUmber of clusters for Kmeans (Int)(Default 20)" )
    parse_cfg = parser.parse_args()
    if parse_cfg.data_dir ==None:
        raise ValueError('An input data directory must be provided')
    if parse_cfg.save_dir ==None:
        raise ValueError('An output data directory must be provided to save constraint maps')
    generate_constraint_maps_batch(parse_cfg)

def generate_constraint_maps_batch(parse_cfg):
    ''' 
    Generates constraint maps for each subject (arranged in a separate folder)
    and saves constraint maps as mat files    
    '''
    datadir = parse_cfg.data_dir                                    # location of pre-processed nii files for pretraining
    num_param_clusters = parse_cfg.numCluster                       # number of clusters for Kmeans, 20 or 30 work well
    opShape = (parse_cfg.opShape,parse_cfg.opShape)                 # output image shape for pretraining
    save_base_dir = parse_cfg.save_dir

    sub_list = natsort.natsorted(os.listdir(datadir))     
 
    # Generate constraint maps for each subject in the training list
    for subName in sub_list:
        print('Subject ', subName)  
        try:
            save_dir = os.path.join(save_base_dir, subName)
            img   = load_unl_brats_img(datadir, subName, opShape)
            print(len(img))
            print('Generating parametric cluster for K=', num_param_clusters)
            kp = generate_parametric_clusters(img, num_cluster=num_param_clusters, random_state=0) 
            pathlib.Path(save_dir).mkdir(parents=True, exist_ok=True)
            temp = {}
            temp['param'] = kp
            
            save_str = '/Constraint_map_' + str(num_param_clusters) + '.mat'

            sio.savemat(save_dir + save_str, temp)
        except:
            print('An exception occured here')


def generate_parametric_clusters(parameter_volume, num_cluster=10, random_state=0,num_PC_2retain=4):
    '''
    Unsupervised KMeans clustering on 3D/4D MR volumes to summarize tissue parameter information 
    in a constraint map. 
    Performs PCA for denoising and dimensionality reduction 
    (if contrast dimension is large in multi-contrast space e.g., T2-weighted TE images for T2 constraint maps)
    Input: Parameter volume (4D) HxWxDxT or (3D) HxWxT where T is the contrast dimension
    Output: Parameter constraint map
    ''' 
    assert len(parameter_volume.shape) == 4
    
    
    xDim, yDim, zDim, tDim = parameter_volume.shape   

    ''' Optional: Use this section to generate a brain mask to avoid including background'''         
    # mask = np.zeros(parameter_volume[...,0].shape)    # optional to generate a mask to avoid including background in constraint maps
    # mask[parameter_volume[...,0] > 0] = 1
    
    
    ''' Perform PCA decomposition'''
    temp_f = np.reshape(parameter_volume,(-1,tDim))
    temp_pc = PCA(n_components=num_PC_2retain).fit_transform((temp_f))
    temp_pc = np.reshape(temp_pc,(xDim,yDim,zDim,num_PC_2retain))
    temp_pc = normalize_img(temp_pc)

    ''' Denoise PC images using TV'''
    for idx in range(num_PC_2retain):            
        temp_pc[...,idx] = performDenoising(temp_pc[...,idx], wts=40)
        # temp_pc[...,idx] = mask * performDenoising(temp_pc[...,idx], wts=40)
        
    img_blk_vec = np.reshape(temp_pc, (-1,num_PC_2retain))
    kmeans = MiniBatchKMeans(n_clusters=num_cluster, random_state=random_state).fit(img_blk_vec)
    class_labels_vec = kmeans.labels_
    param_clusters = np.reshape(class_labels_vec, (xDim,yDim,zDim))               
    return param_clusters

''' Use an appropriate dataloader to load multi-contrast training data
    Example here is for the brain tumor segmentation dataset'''
def load_unl_brats_img(datadir, subName, opShape): 
    ''' Loads a 4D volume from the brats dataset HxWxDxT where the contrasts are [T1Gd, T2w, T1w, T2-FLAIR]'''
    print('Loading MP-MR images for ', subName)
    data_suffix = ['_t1ce.nii.gz', '_t2.nii.gz', '_t1.nii.gz' , '_flair.nii.gz']
    sub_img = []
    for suffix in data_suffix:
        temp = nib.load(datadir + subName + '/' + subName + suffix)
        
        temp = np.rot90(temp.get_fdata(),-1)
        temp = myCrop3D(temp, opShape)
        temp = normalize_img(temp)
        # generate a brain mask from the first volume. If mask is available, skip this step
        if suffix == data_suffix[0]:  
            mask = np.zeros(temp.shape)
            mask[temp > 0] = 1
        # histogram based channel-wise contrast stretching
        temp = contrastStretch(temp, mask, 0.01, 99.9)
        sub_img.append(temp)
    sub_img = np.stack((sub_img), axis=-1)
    return  sub_img 
 

if __name__ == "__main__":
    print('Running generate_constraint_maps.py')
    main()

 