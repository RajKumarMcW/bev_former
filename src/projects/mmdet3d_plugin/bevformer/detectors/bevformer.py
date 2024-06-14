# ---------------------------------------------
# Copyright (c) OpenMMLab. All rights reserved.
# ---------------------------------------------
#  Modified by Zhiqi Li
# ---------------------------------------------

import torch
from mmcv.runner import force_fp32, auto_fp16
from mmdet.models import DETECTORS
from mmdet3d.core import bbox3d2result
from mmdet3d.models.detectors.mvx_two_stage import MVXTwoStageDetector
from projects.mmdet3d_plugin.models.utils.grid_mask import GridMask
import time
import copy
import numpy as np
import mmdet3d
from projects.mmdet3d_plugin.models.utils.bricks import run_time


@DETECTORS.register_module()
class BEVFormer(MVXTwoStageDetector):
    """BEVFormer.
    Args:
        video_test_mode (bool): Decide whether to use temporal information during inference.
    """

    def __init__(self,
                 export=False,
                 ort=False,
                 use_grid_mask=False,
                 pts_voxel_layer=None,
                 pts_voxel_encoder=None,
                 pts_middle_encoder=None,
                 pts_fusion_layer=None,
                 img_backbone=None,
                 pts_backbone=None,
                 img_neck=None,
                 pts_neck=None,
                 pts_bbox_head=None,
                 img_roi_head=None,
                 img_rpn_head=None,
                 train_cfg=None,
                 test_cfg=None,
                 pretrained=None,
                 video_test_mode=False
                 ):

        super(BEVFormer,
              self).__init__(pts_voxel_layer, pts_voxel_encoder,
                             pts_middle_encoder, pts_fusion_layer,
                             img_backbone, pts_backbone, img_neck, pts_neck,
                             pts_bbox_head, img_roi_head, img_rpn_head,
                             train_cfg, test_cfg, pretrained)
        self.export=export
        self.ort=ort
        self.grid_mask = GridMask(
            True, True, rotate=1, offset=False, ratio=0.5, mode=1, prob=0.7)
        self.use_grid_mask = use_grid_mask
        self.fp16_enabled = False

        # temporal
        self.video_test_mode = video_test_mode
        self.prev_frame_info = {
            'prev_bev': None,
            'scene_token': None,
            'prev_pos': 0,
            'prev_angle': 0,
        }


    def extract_img_feat(self, img, img_metas, len_queue=None):
        """Extract features of images."""
        B = img.size(0)
        if img is not None:
            
            # input_shape = img.shape[-2:]
            # # update real input shape of each single img
            # for img_meta in img_metas:
            #     img_meta.update(input_shape=input_shape)

            if img.dim() == 5 and img.size(0) == 1:
                img.squeeze_()
            elif img.dim() == 5 and img.size(0) > 1:
                B, N, C, H, W = img.size()
                img = img.reshape(B * N, C, H, W)
            if self.use_grid_mask:
                img = self.grid_mask(img)

            img_feats = self.img_backbone(img)
            if isinstance(img_feats, dict):
                img_feats = list(img_feats.values())
        else:
            return None
        if self.with_img_neck:
            img_feats = self.img_neck(img_feats)

        img_feats_reshaped = []
        for img_feat in img_feats:
            BN, C, H, W = img_feat.size()
            if len_queue is not None:
                img_feats_reshaped.append(img_feat.view(int(B/len_queue), len_queue, int(BN / B), C, H, W))
            else:
                img_feats_reshaped.append(img_feat.view(B, int(BN / B), C, H, W))
        return img_feats_reshaped

    @auto_fp16(apply_to=('img'))
    def extract_feat(self, img, img_metas=None, len_queue=None):
        """Extract features from images and points."""

        img_feats = self.extract_img_feat(img, img_metas, len_queue=len_queue)
        
        return img_feats


    def forward_pts_train(self,
                          pts_feats,
                          gt_bboxes_3d,
                          gt_labels_3d,
                          img_metas,
                          gt_bboxes_ignore=None,
                          prev_bev=None):
        """Forward function'
        Args:
            pts_feats (list[torch.Tensor]): Features of point cloud branch
            gt_bboxes_3d (list[:obj:`BaseInstance3DBoxes`]): Ground truth
                boxes for each sample.
            gt_labels_3d (list[torch.Tensor]): Ground truth labels for
                boxes of each sampole
            img_metas (list[dict]): Meta information of samples.
            gt_bboxes_ignore (list[torch.Tensor], optional): Ground truth
                boxes to be ignored. Defaults to None.
            prev_bev (torch.Tensor, optional): BEV features of previous frame.
        Returns:
            dict: Losses of each branch.
        """

        outs = self.pts_bbox_head(
            pts_feats, img_metas, prev_bev)
        loss_inputs = [gt_bboxes_3d, gt_labels_3d, outs]
        losses = self.pts_bbox_head.loss(*loss_inputs, img_metas=img_metas)
        return losses

    def forward_dummy(self, img):
        dummy_metas = None
        return self.forward_test(img=img, img_metas=[[dummy_metas]])

    def forward(self, *args,return_loss=True, **kwargs):
        """Calls either forward_train or forward_test depending on whether
        return_loss=True.
        Note this setting will change the expected inputs. When
        `return_loss=True`, img and img_metas are single-nested (i.e.
        torch.Tensor and list[dict]), and when `resturn_loss=False`, img and
        img_metas should be double nested (i.e.  list[torch.Tensor],
        list[list[dict]]), with the outer list indicating test time
        augmentations.
        """
        #mcw
        if self.export:
            img,prev_bev,can_bus,lidar2img=args
            img_metas = [{'can_bus':can_bus, 'lidar2img':lidar2img}]
            return self.forward_export( img,prev_bev=prev_bev,img_metas=img_metas,**kwargs)
        
        if return_loss:
            return self.forward_train(**kwargs)
        else:
            return self.forward_test(**kwargs)
    
    def obtain_history_bev(self, imgs_queue, img_metas_list):
        """Obtain history BEV features iteratively. To save GPU memory, gradients are not calculated.
        """
        self.eval()

        with torch.no_grad():
            prev_bev = None
            bs, len_queue, num_cams, C, H, W = imgs_queue.shape
            imgs_queue = imgs_queue.reshape(bs*len_queue, num_cams, C, H, W)
            img_feats_list = self.extract_feat(img=imgs_queue, len_queue=len_queue)
            for i in range(len_queue):
                img_metas = [each[i] for each in img_metas_list]
                if not img_metas[0]['prev_bev_exists']:
                    prev_bev = None
                # img_feats = self.extract_feat(img=img, img_metas=img_metas)
                img_feats = [each_scale[:, i] for each_scale in img_feats_list]
                prev_bev = self.pts_bbox_head(
                    img_feats, img_metas, prev_bev, only_bev=True)
            self.train()
            return prev_bev

    @auto_fp16(apply_to=('img', 'points'))
    def forward_train(self,
                      points=None,
                      img_metas=None,
                      gt_bboxes_3d=None,
                      gt_labels_3d=None,
                      gt_labels=None,
                      gt_bboxes=None,
                      img=None,
                      proposals=None,
                      gt_bboxes_ignore=None,
                      img_depth=None,
                      img_mask=None,
                      ):
        """Forward training function.
        Args:
            points (list[torch.Tensor], optional): Points of each sample.
                Defaults to None.
            img_metas (list[dict], optional): Meta information of each sample.
                Defaults to None.
            gt_bboxes_3d (list[:obj:`BaseInstance3DBoxes`], optional):
                Ground truth 3D boxes. Defaults to None.
            gt_labels_3d (list[torch.Tensor], optional): Ground truth labels
                of 3D boxes. Defaults to None.
            gt_labels (list[torch.Tensor], optional): Ground truth labels
                of 2D boxes in images. Defaults to None.
            gt_bboxes (list[torch.Tensor], optional): Ground truth 2D boxes in
                images. Defaults to None.
            img (torch.Tensor optional): Images of each sample with shape
                (N, C, H, W). Defaults to None.
            proposals ([list[torch.Tensor], optional): Predicted proposals
                used for training Fast RCNN. Defaults to None.
            gt_bboxes_ignore (list[torch.Tensor], optional): Ground truth
                2D boxes in images to be ignored. Defaults to None.
        Returns:
            dict: Losses of different branches.
        """
        
        len_queue = img.size(1)
        prev_img = img[:, :-1, ...]
        img = img[:, -1, ...]

        prev_img_metas = copy.deepcopy(img_metas)
        prev_bev = self.obtain_history_bev(prev_img, prev_img_metas)

        img_metas = [each[len_queue-1] for each in img_metas]
        if not img_metas[0]['prev_bev_exists']:
            prev_bev = None
        img_feats = self.extract_feat(img=img, img_metas=img_metas)
        losses = dict()
        losses_pts = self.forward_pts_train(img_feats, gt_bboxes_3d,
                                            gt_labels_3d, img_metas,
                                            gt_bboxes_ignore, prev_bev)
        
        losses.update(losses_pts)
        return losses

    def forward_test(self, img_metas, img=None, return_loss=False, rescale=True):
        for var, name in [(img_metas, 'img_metas')]:
            if not isinstance(var, list):
                raise TypeError('{} must be a list, but got {}'.format(
                    name, type(var)))
        img = [img] if img is None else img

        if img_metas[0][0]['scene_token'] != self.prev_frame_info['scene_token']:
            # the first sample of each scene is truncated
            self.prev_frame_info['prev_bev'] = None
        # update idx
        self.prev_frame_info['scene_token'] = img_metas[0][0]['scene_token']

        # do not use temporal information
        if not self.video_test_mode:
            self.prev_frame_info['prev_bev'] = None

        # Get the delta of ego position and angle between two timestamps.
        # mcw
        tmp_pos = copy.deepcopy(img_metas[0][0]['can_bus'][:3])
        tmp_angle = copy.deepcopy(img_metas[0][0]['can_bus'][-1])
        # tmp_pos = img_metas[0][0]['can_bus'][:3]
        # tmp_angle = img_metas[0][0]['can_bus'][-1]
        if self.prev_frame_info['prev_bev'] is not None:
            img_metas[0][0]['can_bus'][:3] -= self.prev_frame_info['prev_pos']
            img_metas[0][0]['can_bus'][-1] -= self.prev_frame_info['prev_angle']
        else:
            img_metas[0][0]['can_bus'][-1] = 0
            img_metas[0][0]['can_bus'][:3] = 0
        # if self.prev_frame_info['prev_bev'] is not None:
        #     print("@@",self.prev_frame_info['prev_bev'].shape)

        #mcw
        # torch.manual_seed(42)
        # # print(img_metas[0][0])
        # # print(img[0])
        # # exit()
        # if self.prev_frame_info['prev_bev']==None:
        #     self.prev_frame_info['prev_bev'] = torch.zeros(2500, 1, 256).cuda()
        # can_bus = torch.tensor(np.fromfile("/media/ava/DATA2/Raj/BEVFormer/artifacts/can_bus.npy", dtype=np.float32))
        # lidar2img = torch.tensor(np.fromfile("/media/ava/DATA2/Raj/BEVFormer/artifacts/lidar2img.npy", dtype=np.float32)).reshape(1,6,4,4)
        # # lidar2img = lidar2img[:,:6]
        # img_metas[0][0]['can_bus']=can_bus.numpy()
        # img_metas[0][0]['lidar2img']=[l.numpy() for l in lidar2img[0]]
        # print(img_metas[0][0]['can_bus'],img_metas[0][0]['lidar2img'])
        # exit()

        new_prev_bev, bbox_results = self.simple_test(
            img_metas[0], img[0], prev_bev=self.prev_frame_info['prev_bev'], rescale=True)
        # During inference, we save the BEV features and ego motion of each timestamp.
        self.prev_frame_info['prev_pos'] = tmp_pos
        self.prev_frame_info['prev_angle'] = tmp_angle
        self.prev_frame_info['prev_bev'] = new_prev_bev
        return bbox_results

    def simple_test_pts(self, x, img_metas, prev_bev=None, rescale=False):
        """Test function"""
        outs = self.pts_bbox_head(x, img_metas, prev_bev=prev_bev)
        #mcw
        # print(outs)
        # for key, tensor in outs.items():
        #     if tensor==None:
        #         continue
        #     np_array = tensor.cpu().numpy()
        #     file_path = f"{key}.npy"
        #     np.save(file_path, np_array)
        # exit()

        bbox_list = self.pts_bbox_head.get_bboxes(
            outs, img_metas, rescale=rescale)
        bbox_results = [
            bbox3d2result(bboxes, scores, labels)
            for bboxes, scores, labels in bbox_list
        ]
        return outs['bev_embed'], bbox_results

    def simple_test(self, img_metas, img=None, prev_bev=None, rescale=False):
        """Test function without augmentaiton."""
        # print("@@",img,img_metas,prev_bev)
        
        if self.ort:
            import onnxruntime as ort
            img=img.unsqueeze(0)
            can_bus = torch.tensor(img_metas[0]['can_bus'],dtype=torch.float64)
            lidar2img = img_metas[0]['lidar2img']
            lidar2img = torch.tensor(lidar2img).reshape(1,6,4,4)
            lidar2img = lidar2img[:,:6]
            if prev_bev==None:
                sess=ort.InferenceSession("/media/ava/DATA2/Raj/BEVFormer/simplified_model_withoutprevbev.onnx",providers=['CUDAExecutionProvider'])
                inputs = {
                            'img.1': img.cpu().numpy(),
                            'onnx::Unsqueeze_1': can_bus.cpu().numpy(),
                            'onnx::Cast_2': lidar2img.cpu().numpy()
                        }
                output=sess.run(None, inputs)
            else:
                # sess_options = ort.SessionOptions()
                # sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
                # sess_options.log_severity_level=1
                sess=ort.InferenceSession("/media/ava/DATA2/Raj/BEVFormer/simplified_model_withprevbev.onnx",providers=['CUDAExecutionProvider'])
                inputs = {
                            'img.1': img.cpu().numpy(),
                            'onnx::Gather_1': prev_bev.cpu().numpy(),
                            'onnx::Gather_2': can_bus.cpu().numpy(),
                            'onnx::Cast_3': lidar2img.cpu().numpy()
                        }
                output=sess.run(None, inputs)
                
            output={'bev_embed':torch.tensor(output[0]).cuda(),'all_cls_scores':torch.tensor(output[1]).cuda(),
             'all_bbox_preds':torch.tensor(output[2]).cuda(),'enc_cls_scores': None, 'enc_bbox_preds': None}
            # print(output)
            # exit()
            bbox_list = [dict() for i in range(len(img_metas))]
            bbox_lists = self.pts_bbox_head.get_bboxes(
                output, img_metas, rescale=rescale)
            bbox_results = [
                bbox3d2result(bboxes, scores, labels)
                for bboxes, scores, labels in bbox_lists
            ]
            for result_dict, pts_bbox in zip(bbox_list, bbox_results):
                result_dict['pts_bbox'] = pts_bbox
            return output['bev_embed'], bbox_list
        else:
            img_feats = self.extract_feat(img=img, img_metas=img_metas)
            # print("@@")
            # print(img_feats)
            # exit()
            
            bbox_list = [dict() for i in range(len(img_metas))]
            new_prev_bev, bbox_pts = self.simple_test_pts(
                img_feats, img_metas, prev_bev, rescale=rescale)
            for result_dict, pts_bbox in zip(bbox_list, bbox_pts):
                result_dict['pts_bbox'] = pts_bbox
            return new_prev_bev, bbox_list

    # mcw
    def forward_export(self, img,prev_bev,img_metas):
        out=self.simple_export(
            img_metas, img[0], prev_bev=prev_bev, rescale=True)
        return out

    def simple_export(self, img_metas, img=None, prev_bev=None, rescale=False):
        """Test function without augmentaiton."""
        # print("@@",img,img_metas,prev_bev)
        img_feats = self.extract_feat(img=img, img_metas=img_metas) #torch.Size([1, 6, 256, 15, 25])
        
        # bbox_list = [dict() for i in range(len(img_metas))]
        # new_prev_bev, bbox_pts = self.simple_test_pts_export(
        #     img_feats, img_metas, prev_bev, rescale=rescale)
        # for result_dict, pts_bbox in zip(bbox_list, bbox_pts):
        #     result_dict['pts_bbox'] = pts_bbox
        # return new_prev_bev, bbox_list
        # mcw
        # print("@@")
        # print(img_feats)
        # exit()
        # print("@@",prev_bev)
        out = self.pts_bbox_head(img_feats, img_metas, prev_bev=prev_bev,export=True)
        return out
    
    # def extract_img_feat_export(self, img, img_metas, len_queue=None):
    #     """Extract features of images."""
    #     B = img.size(0)
    #     if img is not None:
            
    #         # input_shape = img.shape[-2:]
    #         # # update real input shape of each single img
    #         # for img_meta in img_metas:
    #         #     img_meta.update(input_shape=input_shape)

    #         if img.dim() == 5 and img.size(0) == 1:
    #             img.squeeze_()
    #         elif img.dim() == 5 and img.size(0) > 1:
    #             B, N, C, H, W = img.size()
    #             img = img.reshape(B * N, C, H, W)
    #         if self.use_grid_mask:
    #             img = self.grid_mask(img)

            
    #         img_feats = self.img_backbone(img)
    #         if isinstance(img_feats, dict):
    #             img_feats = list(img_feats.values())
    #     else:
    #         return None
    #     if self.with_img_neck:
    #         img_feats = self.img_neck(img_feats)

    #     img_feats_reshaped = []
    #     for img_feat in img_feats:
    #         BN, C, H, W = img_feat.size()
    #         if len_queue is not None:
    #             img_feats_reshaped.append(img_feat.view(int(B/len_queue), len_queue, int(BN / B), C, H, W))
    #         else:
    #             img_feats_reshaped.append(img_feat.view(B, int(BN / B), C, H, W))
    #     return img_feats_reshaped

    # @auto_fp16(apply_to=('img'))
    # def extract_feat_export(self, img, img_metas=None, len_queue=None):
    #     """Extract features from images and points."""

    #     img_feats = self.extract_img_feat_export(img, img_metas, len_queue=len_queue)
        
    #     return img_feats

