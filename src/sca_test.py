# from src.projects.mmdet3d_plugin.bevformer.modules import SpatialCrossAttention
# import torch

# query = torch.rand([1, 2500, 256])
# key=torch.rand([6, 375, 1, 256])
# value=torch.rand([6, 375, 1, 256])
# residual=None
# query_pos=None
# key_padding_mask=None
# reference_points=torch.rand([1, 4, 2500, 3])
# spatial_shapes=torch.rand([1, 2])
# reference_points_cam=torch.rand([6, 1, 2500, 4, 2])
# bev_mask=torch.randint(0, 2, [6, 1, 2500, 4], dtype=torch.bool)
# level_start_index=torch.tensor([0])
# flag="encoder"
# print("@@",query,query.shape,
#                 key,key.shape,
#                 value,value.shape,
#                 residual,#residual.shape,
#                 query_pos,#query_pos.shape,
#                 key_padding_mask,#key_padding_mask.shape,
#                 reference_points,reference_points.shape,
#                 spatial_shapes,spatial_shapes.shape,
#                 reference_points_cam,reference_points_cam.shape,
#                 bev_mask,bev_mask.shape,
#                 level_start_index,level_start_index.shape,
#                 flag)
# SpatialCrossAttention(query,
#                 key,
#                 value,
#                 residual,
#                 query_pos,
#                 key_padding_mask,
#                 reference_points,
#                 spatial_shapes,
#                 reference_points_cam,
#                 bev_mask,
#                 level_start_index,
#                 flag)
# (
#                     query,
#                     key,
#                     value,
#                     identity if self.pre_norm else None,
#                     query_pos=query_pos,
#                     key_pos=key_pos,
#                     reference_points=ref_3d,
#                     reference_points_cam=reference_points_cam,
#                     mask=mask,
#                     attn_mask=attn_masks[attn_index],
#                     key_padding_mask=key_padding_mask,
#                     spatial_shapes=spatial_shapes,
#                     level_start_index=level_start_index,
#                     **kwargs)

# print("@@",self.attentions[attn_index],
#                     query,query.shape,
#                     key,key.shape,
#                     value,value.shape,
#                     identity,identity.shape,
#                     # query_pos,query_pos.shape,
#                     # key_pos,key_pos.shape,
#                     ref_3d,ref_3d.shape,
#                     reference_points_cam,reference_points_cam.shape,
#                     # mask,mask.shape,
#                     # attn_masks[attn_index],attn_masks[attn_index].shape,
#                     # key_padding_mask,key_padding_mask.shape,
#                     spatial_shapes,spatial_shapes.shape,
#                     level_start_index,level_start_index.shape,
#                     )