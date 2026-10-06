"""Perps the ranker never holds (spec 2026-10-02 §1.1), decided by what each ticker is.

Frozen before any model run and reviewed by the owner. It was drafted on 2026-10-05 from the
archive's 900 USDT perps. TRADFI is every contract Binance's exchangeInfo labels
TRADIFI_PERPETUAL; the other sets come from the tickers' names. No price, volume or return
informed any entry. A ticker excluded here is excluded in every listing it has. TradFi contracts
listed after 2026-10-05 have no bars inside Experiment 1's windows, so the list is complete for
this experiment; the paper phase amends it.

Kept on purpose, for the owner to confirm:
- USTCUSDT, a stablecoin that lost its peg in 2022 and now trades like any token;
- FRAXUSDT, STABLEUSDT, STBLUSDT and USUALUSDT, tokens of stablecoin projects rather than
  stablecoins;
- PUMPBTCUSDT, a governance token that is not pegged to BTC.
"""

STABLECOINS = frozenset({"USDCUSDT"})

# Tokens backed by gold: they track a commodity, not crypto.
PEGGED = frozenset({"PAXGUSDT", "XAUTUSDT"})

# Composite contracts. Binance's exchangeInfo marks the first three INDEX; the rest are delisted.
INDEXES = frozenset({
    "ALLUSDT", "BTCDOMUSDT", "DEFIUSDT",
    "BLUEBIRDUSDT", "DOTECOUSDT", "FOOTBALLUSDT",
})

# Binance's TRADIFI_PERPETUAL contracts in the archive, grouped by its underlyingType.
TRADFI = frozenset({
    # CN_EQUITY (2)
    "CXMTUSDT", "UNITREEUSDT",
    # COMMODITY (8)
    "BZUSDT", "CLUSDT", "COPPERUSDT", "NATGASUSDT", "XAGUSDT", "XAUUSDT", "XPDUSDT", "XPTUSDT",
    # EQUITY (174), stocks and ETFs
    "AAOIUSDT", "AAPLUSDT", "ACNUSDT", "ADBEUSDT", "AGPUUSDT", "ALABUSDT", "AMATUSDT",
    "AMCUSDT", "AMDUSDT", "AMZNUSDT", "ANETUSDT", "APLDUSDT", "APPUSDT", "ARMUSDT", "ASMLUSDT",
    "ASTSUSDT", "AVGOUSDT", "AXTIUSDT", "BABAUSDT", "BBXUSDT", "BEUSDT", "BITOUSDT", "BMNRUSDT",
    "BNCUSDT", "BOTUSDT", "BRKBUSDT", "BSPUSDT", "BWETUSDT", "BXUSDT", "CATUSDT", "CBRSUSDT",
    "CIENUSDT", "COHRUSDT", "COINUSDT", "COSTUSDT", "CRCLUSDT", "CRDOUSDT", "CRMLUSDT",
    "CRMUSDT", "CRWDUSDT", "CRWVUSDT", "CSCOUSDT", "CVNAUSDT", "CYPHUSDT", "DDOGUSDT",
    "DELLUSDT", "DISUSDT", "DJTUSDT", "DKNGUSDT", "DRAMUSDT", "EBAYUSDT", "EWJUSDT", "EWTUSDT",
    "EWYUSDT", "EWZUSDT", "FLEXUSDT", "FLNCUSDT", "FWDIUSDT", "GDXUSDT", "GEVUSDT", "GLWUSDT",
    "GMEUSDT", "GOOGLUSDT", "GPROUSDT", "GSUSDT", "GTLBUSDT", "HDUSDT", "HIMSUSDT", "HOODUSDT",
    "HPEUSDT", "HUTUSDT", "IBMUSDT", "INTCUSDT", "INTWUSDT", "IONQUSDT", "IRENUSDT", "IWMUSDT",
    "JPMUSDT", "KLACUSDT", "KORUUSDT", "KOUSDT", "KSTRUSDT", "LITEUSDT", "LLYUSDT", "LRCXUSDT",
    "LYTEUSDT", "MARAUSDT", "MDBUSDT", "METAUSDT", "MPUSDT", "MRKUSDT", "MRNAUSDT", "MRVLUSDT",
    "MSFTUSDT", "MSTRUSDT", "MUUSDT", "MUUUSDT", "MVLLUSDT", "NBISUSDT", "NETUSDT", "NFLXUSDT",
    "NKEUSDT", "NOKUSDT", "NOWUSDT", "NVDAUSDT", "NVDLUSDT", "NVOUSDT", "OKLOUSDT", "ONDSUSDT",
    "ORCLUSDT", "PANWUSDT", "PATHUSDT", "PAYPUSDT", "PDDUSDT", "PENGUSDT", "PLTRUSDT",
    "PYPLUSDT", "QCOMUSDT", "QNTXUSDT", "QQQUSDT", "RAMUSDT", "RDDTUSDT", "RIVNUSDT",
    "RKLBUSDT", "RUMUSDT", "SECZUSDT", "SHAZUSDT", "SHOPUSDT", "SKDDUSDT", "SKHYUSDT",
    "SKUUUSDT", "SMCIUSDT", "SMHUSDT", "SNDKUSDT", "SNOWUSDT", "SNXXUSDT", "SOFIUSDT",
    "SONYUSDT", "SOXLUSDT", "SOXSUSDT", "SPCXUSDT", "SPYUSDT", "SQQQUSDT", "STRCUSDT",
    "STXXUSDT", "TBTUSDT", "TEAMUSDT", "TEMUSDT", "TERUSDT", "TMFUSDT", "TQQQUSDT", "TSLAUSDT",
    "TSLLUSDT", "TSMUSDT", "TTWOUSDT", "TWSTUSDT", "TXNUSDT", "TZAUSDT", "UBERUSDT", "UNHUSDT",
    "URNMUSDT", "USARUSDT", "UVXYUSDT", "VRTUSDT", "VSTUSDT", "VUSDT", "WDCUSDT", "WENUSDT",
    "WMTUSDT", "XBIUSDT", "XLEUSDT", "XOMUSDT", "ZMUSDT", "ZSUSDT",
    # FX (1)
    "USDBRLUSDT",
    # HK_EQUITY (15)
    "BYDUSDT", "CSOPSAMSUNG2LUSDT", "CSOPSKHYNIX2LUSDT", "GIGADEVUSDT", "HK0625USDT",
    "HK0700USDT", "HK0992USDT", "HK1810USDT", "KUAISHOUUSDT", "MEITUANUSDT", "MINIMAXUSDT",
    "POPMARTUSDT", "TENCENTUSDT", "ZHIPUUSDT", "ZHONGJIUSDT",
    # KR_EQUITY (8)
    "HANMIUSDT", "HYUNDAIUSDT", "KODEX200USDT", "LGELECTRONICSUSDT", "NAVERUSDT",
    "SAMSUNGEMUSDT", "SAMSUNGUSDT", "SKHYNIXUSDT",
    # PREMARKET (4), pre-IPO company valuations
    "ANTHROPICUSDT", "MOONSHOTUSDT", "OPENAIUSDT", "OURAUSDT",
})

EXCLUDED = STABLECOINS | PEGGED | INDEXES | TRADFI
