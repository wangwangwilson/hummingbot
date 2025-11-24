#!/bin/bash
# 后台运行网格搜索脚本

cd /home/wilson/hummingbot/numba_bt
nohup python3 tests/grid_search_as_model_future.py > grid_search.log 2>&1 &
echo "网格搜索已在后台启动，PID: $!"
echo "查看进度: tail -f grid_search.log"
echo "查看进程: ps aux | grep grid_search"

