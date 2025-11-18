好的，这是一份基于您提供的 SSRN 论文（*Market Making in Crypto, 2024*）的详细策略拆解报告。

本文的核心是开发并实盘验证了一种新的做市 Alpha 信号，名为 **Bar Portion (BP)**，并证明了它优于 Hummingbot 平台默认的 **MACD** 信号。

---

### 1. 核心策略：PMM BP (Pure Market Making + Bar Portion)

论文的最终策略是 **PMM BP**，这是对 Hummingbot 平台现有 `PMM Dynamic` 策略的改进版。`PMM Dynamic` 是一种动态做市策略，它使用 **MACD** 信号来调整其参考中间价，并使用 **NATR**（波动率）来调整价差。

PMM BP 策略的核心逻辑是：**用新开发的 “Bar Portion (BP)” 信号取代原版的 MACD 信号**，以更有效地预测短期价格方向，从而调整（Skew）做市报价。

### 2. Bar Portion (BP) 策略详解

#### A. 计算逻辑
BP 信号是一个基于 K 线数据计算的、用于预测短期均值回归的因子。

* **数据：** 1 分钟 K 线（Candlestick）数据。
* **因子公式：**
    `BP = (Close - Open) / (High - Low)`
* **值域：** -1 到 +1。
    * `BP = +1` 意味着是一根极强的大阳线（Open=Low, Close=High）。
    * `BP = -1` 意味着是一根极强的大阴线（Open=High, Close=Low）。

#### B. 策略逻辑 (Alpha)
BP 信号的核心逻辑是**均值回归 (Mean Reversion)**。

论文通过五分位分析（Quintile Analysis）发现（见 Figure 10 & 13），BP 信号与未来收益呈**单调递减**关系：

1.  **当 BP 值很高时 (e.g., > 0.7)：**
    * **市场状态：** 价格在 1 分钟内被迅速拉升（大阳线）。
    * **策略预测：** 市场大概率会**回调（下跌）**。
    * **做市动作：** 策略会**向下偏斜 (Skew Down)** 其参考中间价。即降低买单报价、更积极地设置卖单，以期望卖出（做空）并捕捉即将到来的回调。

2.  **当 BP 值很低时 (e.g., < -0.7)：**
    * **市场状态：** 价格在 1 分钟内被迅速砸下（大阴线）。
    * **策略预测：** 市场大概率会**反弹（上涨）**。
    * **做市动作：** 策略会**向上偏斜 (Skew Up)** 其参考中间价。即提高买单报价、更积极地设置买单，以期望买入（做多）并捕捉即将到来的反弹。

3.  **当 BP 值接近 0 时：**
    * **市场状态：** 市场处于平衡（十字星）。
    * **策略预测：** 价格将保持稳定。
    * **做市动作：** 策略保持中性报价，对称地挂在市场中间价两侧。

#### C. 数据与参数
PMM BP 策略的参数主要分为两类：**风险管理参数**（通过 Optuna 优化）和**信号参数**。

| 参数类别 | 参数名称 | 详细说明与论文发现 |
| :--- | :--- | :--- |
| **信号 (Alpha)** | `Alpha Signal` | 使用 **Bar Portion (BP)** 信号。 |
| | `Data Frequency` | **1 分钟** K 线数据。 |
| **风险 (Risk)** | `Stop Loss (SL)` | 三重障碍（Triple Barrier）的止损阈值。 |
| | `Take Profit (TP)` | 止盈阈值。 |
| | `Time Limit` | 持仓时间限制（在参数重要性分析中，此项**最重要**，见 Figure 8）。 |
| | **发现：** SL 和 TP 与月度波动率**无关** (R² ≈ 0)，必须独立优化 (Figure 19, 20)。 |
| **价差 (Spread)** | `Start Spread` | 距离中间价的第一档价差。 |
| | `Step Spread` | 多档订单之间的步进价差。 |
| | **发现：** 价差与月度波动率**强正相关** (R² ≈ 0.88)。优化的价差约为**月度波动率的 4-5 倍** (Figure 17, 18)。 |
| | `NATR Length` | (继承自 PMM Dynamic) 用于衡量短期波动率以调整价差。 |
| **执行 (Execution)** | `Executor Refresh Time` | 策略刷新（检查市场和调整订单）的频率。回测优化为 **3-5 分钟** (Section 3.1.2)。 |
| | `Stop Loss Cooldown Time`| 止损触发后的冷却时间。回测优化为 **8-9 分钟** (Section 3.1.2)。 |

---

### 3. 基线策略：MACD (PMM Dynamic) 详解

PMM BP 策略所对比的基线是 Hummingbot 平台内置的 `PMM Dynamic` 策略。

#### A. 策略逻辑
`PMM Dynamic` 策略试图通过两个技术指标来动态调整做市行为：

1.  **参考中间价调整：** 使用 **MACD** 信号来预测**趋势 (Momentum)**。
    * 当 MACD 发出金叉或看涨信号时，策略会**向上偏斜 (Skew Up)** 参考价，试图多做多。
    * 当 MACD 发出死叉或看跌信号时，策略会**向下偏斜 (Skew Down)** 参考价，试图多做空。
2.  **价差调整：** 使用 **NATR (归一化平均真实波幅)** 来调整价差。
    * 当波动率（NATR）上升时，**扩大**价差以降低风险。
    * 当波动率（NATR）下降时，**缩小**价差以增加成交概率。

#### B. 参数
| 参数名称 | 详细说明 |
| :--- | :--- |
| `MACD Fast` | MACD 的短期 EMA 周期 (e.g., 12)。 |
| `MACD Slow` | MACD 的长期 EMA 周期 (e.g., 26)。 |
| `MACD Signal`| MACD 的信号线 EMA 周期 (e.g., 9)。 |
| `NATR Length`| NATR 的计算周期。 |
| (其他参数) | 共享 PMM Simple 的风险和执行参数（如 SL, TP, Time Limit 等）。 |

---

### 4. 论文效果与结论

论文通过**定向回测**和**实盘交易**两个阶段证明了 BP 策略的有效性。

#### A. 定向回测 (Alpha 验证)
在 9 天的回测期内，对比 BP 和 MACD 作为**纯定向信号**（非做市）的表现：

| 信号 (策略) | 夏普比率 (Sharpe) | 累计回报 (Return) | 最大回撤 (MDD) |
| :--- | :--- | :--- | :--- |
| **Bar Portion (BP)** | **0.78** | **+45.84%** | -3.94% |
| **MACD** | -0.01 | -0.59% | -8.71% |

**结论：** BP 信号（均值回归）的预测能力**远超** MACD 信号（趋势）。

#### B. 实盘交易 (24小时, OKX)
对比 `PMM BP` (新策略) 和 `PMM Dynamic` (基线/MACD) 在**真实做市**环境下的净 PnL：

| 交易对 | PMM BP (新策略) PnL | PMM Dynamic (基线) PnL | 结果 |
| :--- | :--- | :--- | :--- |
| **SOL-USDT** | **$1.21** (盈利) | -$1.59 (亏损) | **BP 胜利** |
| **DOGE-USDT**| $3.19 (盈利) | $3.22 (盈利) | **打平** |
| **GALA-USDT**| -$6.56 (亏损) | -$9.78 (亏损) | **BP 亏损更少** |

**最终效果：** PMM BP 策略在所有测试中均优于或等于 PMM Dynamic (MACD) 策略，证明了 BP 信号是一个更稳健的 Alpha 因子。

---

### 5. 如何复现该策略

要复现这篇论文，您需要以下原始数据：

1.  **核心数据：1 分钟 K 线 (Candlestick) 数据**
    * **数据源：** Binance (币安) (Section 2.3)。
    * **时间范围：** 2024 年 9 月 1 日至 2024 年 10 月 14 日 (45 天) (Section 2.3)。
    * **品种：** 论文中提到的 30 种加密货币永续合约 (Section 2.1)。
    * **数据字段 (必须)：** `open_time`, `open`, `high`, `low`, `close`, `volume`, `close_time`, `quote_volume`, `count`, `taker_buy_volume`, `taker_buy_quote_volume` (Section 2.3, Figure 4)。
2.  **软件：**
    * **Hummingbot**：用于运行 PMM Simple, PMM Dynamic 和 PMM BP 策略的开源框架。
    * **Optuna**：用于进行参数优化的 Python 库。
3.  **关键参数信息：**
    * 您需要使用 Optuna 来复现作者的优化过程，以找到 `Stop Loss`, `Take Profit` 和 `Time Limit` 的具体值。
    * `Spread` 参数可以根据论文的发现，设为**月度波动率的 4-5 倍**作为起始点。