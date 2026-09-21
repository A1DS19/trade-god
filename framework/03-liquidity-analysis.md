# Liquidity Analysis System

Source: https://www.skool.com/coinpicksgenesis/classroom/eed2ad74?md=d46fdc6a21a14a8399d2afb4491eebe3

We measure liquidity in only two ways:
1. The size of the **liquidity pool**
2. The **±2% liquidity depth**

To determine if a coin's liquidity is small, we compare it to the **pre-pump liquidity of recent top performers**, giving us a real-time benchmark for what "cheap" looks like in the current cycle.

From this, we build a liquidity matrix that maps volatility: assets with lower liquidity tend to move faster in both directions, while higher liquidity assets move more slowly and with more stability.

Don't overthink the liquidity tier—there's no perfect formula, just make your best guess between **low, medium, or high risk**, move forward, and you'll get better at spotting the difference with experience.

> Hypothetical Liquidity Matrix (Example Only — Subject to Market Conditions 07/11/2025)

---

## Liquidity-Based Risk Management

🟩 **Liquidity-Based Buying Strategy**

We buy more cautiously in volatile, low-liquidity environments and more aggressively in stable, high-liquidity conditions.

**Key Logic: Liquidity-Based Risk Management**

- **Low Liquidity = High Volatility.** These coins can move fast in both directions, so we **scale in cautiously and exit aggressively**.
- **High Liquidity = Low Volatility.** These assets move more steadily, so we **enter with greater confidence and scale out more gradually**.

**Buying Strategy:** The more volatile and illiquid the coin, the more conservative and spread out our entries.

**Selling Strategy:** The more volatile and illiquid the coin, the more aggressive and front-loaded our exits.

**Liquidity is our Risk Signal.** It determines both how much we deploy and how we manage position flow on the way in and out.

---

## How to Determine Liquidity Tier (from One Page Report Framework)

1. Check the **"Markets" tab on CoinGecko**.
2. Press the **"+2% Depth"** column to rank exchanges by ±2% depth.
3. Find the **main DEX liquidity pool** for the coin (usually on GeckoTerminal).
4. Click through the top 3–5 pools by liquidity — sometimes the preview is outdated.
5. Use the highest pool's TVL + the ±2% depth across exchanges to assign **Low / Medium / High**.

If a coin has no DEX pool, assign tier based only on ±2% depth across CEXs.
