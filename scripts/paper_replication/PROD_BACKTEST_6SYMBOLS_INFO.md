# 正式Prod回测信息

## 回测配置

### 交易对
- ASTER-USDT
- BTC-USDT
- ETH-USDT
- PUMP-USDT
- SOL-USDT
- XRP-USDT

**总计**: 6个交易对

### 回测区间
- **开始日期**: 2025-01-01
- **结束日期**: 2025-11-09
- **时长**: 约10个月

### 数据配置
- **基础数据**: 1分钟K线（从本地zip文件读取）
- **回测分辨率**: 15分钟K线（从1分钟数据重采样）
- **画图频率**: 3分钟

### 策略配置
每个交易对运行3种策略：
1. **PMM Simple** - 经典做市策略
2. **PMM Dynamic (MACD)** - MACD动态做市策略
3. **PMM Bar Portion** - Bar Portion做市策略

**总计**: 6个交易对 × 3种策略 = **18个回测任务**

### 手续费设置
- **Maker费率**: 0.0% (万0)
- **Taker费率**: 0.02% (万2)

### 并行配置
- **并行模式**: joblib multiprocessing
- **工作进程数**: -1 (使用所有CPU核心)
- **预计并行度**: 14个并发工作进程

### 输出配置
- **环境**: prod
- **输出目录**: `backtest_results/prod/{timestamp}/`
- **文件结构**:
  ```
  backtest_results/prod/{timestamp}/
    {SYMBOL}/
      {SYMBOL}_prod.json
      {SYMBOL}_prod_{STRATEGY}_plots.png
      {SYMBOL}_prod_{STRATEGY}_data.csv
  ```

## 预计执行时间

### 数据准备阶段
- 每个交易对需要准备数据（从1分钟重采样到15分钟）
- 预计：1-2分钟/交易对

### 回测执行阶段
- 18个回测任务并行执行
- 每个任务预计：10-20分钟（取决于数据量和策略复杂度）
- 并行执行，预计总时间：20-30分钟

### 总预计时间
- **数据准备**: 6-12分钟
- **回测执行**: 20-30分钟
- **总计**: **约30-45分钟**

## 监控命令

### 查看回测进程
```bash
ps aux | grep backtest_with_plots_and_structure.py
```

### 查看回测日志
```bash
tail -f prod_backtest_6symbols_20250101_20251109.log
```

### 查看最新进度
```bash
tail -50 prod_backtest_6symbols_20250101_20251109.log | grep -E "(Done|elapsed|remaining|Step|完成)"
```

### 查看输出目录
```bash
ls -lth backtest_results/prod/ | head -5
```

## 注意事项

1. **数据完整性**
   - PUMP-USDT的2025-11-01到2025-11-09数据可能缺失（zip文件损坏）
   - 其他交易对的数据完整性需要验证

2. **资源使用**
   - 回测会使用所有CPU核心
   - 内存使用量可能较高（每个进程约500MB-1GB）
   - 建议在系统资源充足时运行

3. **结果验证**
   - 回测完成后，检查每个交易对的JSON、CSV和PNG文件
   - 验证仓位曲线、PnL曲线和统计指标
   - 对比不同策略的表现

## 回测启动时间
**2025-11-14 20:15**

## 状态
✅ **已启动**

