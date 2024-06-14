#!/usr/bin/env bash

CONFIG=$1
CHECKPOINT=$2
GPUS=$3
EXPORT=$4
PORT1=${PORT:-29669}
PORT2=${PORT:-24443}

if [ "$EXPORT" = "true" ]; then
    PYTHONPATH="$(dirname $0)/..":$PYTHONPATH \
    python -m torch.distributed.launch --nproc_per_node=$GPUS --master_port=$PORT1 \
        $(dirname "$0")/export.py $CONFIG $CHECKPOINT --launcher pytorch ${@:5}
else
    PYTHONPATH="$(dirname $0)/..":$PYTHONPATH \
    python -m torch.distributed.launch --nproc_per_node=$GPUS --master_port=$PORT2 \
        $(dirname "$0")/test.py $CONFIG $CHECKPOINT --launcher pytorch ${@:5} --eval bbox
fi
