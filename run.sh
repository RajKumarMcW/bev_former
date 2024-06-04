# val 
src/tools/dist_test.sh configs/bevformer/bevformer_tiny.py \
    artifacts/bevformer_tiny_epoch_24.pth 1 "false" 2>&1 | tee log/crossattention.log

# export
# src/tools/dist_test.sh configs/bevformer/bevformer_tiny.py \
#     artifacts/bevformer_tiny_epoch_24.pth 1 "true" 2>&1 | tee log/cexportnew.log


# train
# src/tools/dist_train.sh configs/bevformer/bevformer_tiny.py 1 2>&1 | tee log/train7.log
