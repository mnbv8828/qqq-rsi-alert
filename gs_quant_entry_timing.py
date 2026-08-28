def calculate_entry_timing(df, benchmark):
    x = df.iloc[-1]
    p = df.iloc[-2]
    score = 0

    # RSI: looking for pullback/recovery, not simply low RSI
    if x["RSI"] <= 35:
        score += 15
    elif x["RSI"] <= 40:
        score += 10
    elif 40 < x["RSI"] <= 55:
        score += 5

    if x["RSI"] > p["RSI"]:
        score += 10

    # MACD
    if x["MACD"] > x["MACD_SIGNAL"]:
        score += 10

    if p["MACD"] <= p["MACD_SIGNAL"] and x["MACD"] > x["MACD_SIGNAL"]:
        score += 10

    # Moving averages
    if x["Close"] > x["MA20"]:
        score += 10

    if p["Close"] <= p["MA20"] and x["Close"] > x["MA20"]:
        score += 10

    if x["Close"] > x["MA50"]:
        score += 5

    # Volume confirmation
    if x["VOL_RATIO"] >= 1.2:
        score += 5

    # QQQ regime confirmation
    bx = benchmark.iloc[-1]
    bp = benchmark.iloc[-2]

    if bx["RSI"] > bp["RSI"]:
        score += 5

    if bx["Close"] > bx["MA20"]:
        score += 5

    return min(int(score), 100)
