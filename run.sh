# val 
# src/tools/dist_test.sh configs/bevformer/bevformer_tiny.py \
#     artifacts/bevformer_tiny_epoch_24.pth 1 "false" 2>&1 | tee log/fullds3.log

# export
src/tools/dist_test.sh configs/bevformer/bevformer_tiny.py \
    artifacts/bevformer_tiny_epoch_24.pth 1 "true" 2>&1 | tee log/check_export3.log


# train
# src/tools/dist_train.sh configs/bevformer/bevformer_tiny.py 1 2>&1 | tee log/train5.log
