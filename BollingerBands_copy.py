# -*- coding:utf-8 -*-

from CloudQuant import MiniSimulator
import numpy as np
import pandas as pd

username = 'Harvey_Sun'
password = 'P948894dgmcsy'
Strategy_Name = 'BollingerBands'

INIT_CAP = 100000000
START_DATE = '20130101'
END_DATE = '20161231'
Fee_Rate = 0.001


def initial(sdk):
    # 下载日度最高价、最低价和中证500成分股
    sdk.prepareData(['LZ_GPA_QUOTE_TCLOSE', 'LZ_GPA_INDEX_CSI500MEMBER',
                     'LZ_GPA_SLCIND_STOP_FLAG'])
    # 下面获取close数据是为了判断某些股票当天是否已退市
    close = pd.read_csv('C:\cStrategy\Factor\LZ_GPA_QUOTE_TCLOSE.csv', index_col=0)
    close.index = [str(i) for i in close.index]
    sdk.setGlobal('close', close)
    # 获取股票代码
    stock_list = sdk.getStockList()
    sdk.setGlobal('stock_list', stock_list)
    # 找到中证500成分股
    in_zz500_yes = pd.Series(sdk.getFieldData('LZ_GPA_INDEX_CSI500MEMBER')[-1]) == 1
    zz500_yes = list(pd.Series(stock_list)[in_zz500_yes])
    sdk.setGlobal('zz500_yes', zz500_yes)
    # 建立一个字典来管理每只股票的仓位信息
    cash_for_each_stock = INIT_CAP / 500
    position_of_stock = {}
    for stock in zz500_yes:
        position_of_stock[stock] = {}
        position_of_stock[stock]['position'] = 0
        position_of_stock[stock]['cash'] = cash_for_each_stock
        # position_of_stock[stock]['last_trade_day'] = str(int(START_DATE) - 1)
    sdk.setGlobal('position_of_stock', position_of_stock)
    # 辅助变量设置
    new_stock = []
    stock_with_position = []
    sdk.setGlobal('new_stock', new_stock)
    sdk.setGlobal('stock_with_position', stock_with_position)


def init_per_day(sdk):
    close = sdk.getGlobal('close')
    today = sdk.getNowDate()
    # 获取股票仓位信息
    position_of_stock = sdk.getGlobal('position_of_stock')
    # 获取当天中证500成分股
    in_zz500_today = pd.Series(sdk.getFieldData('LZ_GPA_INDEX_CSI500MEMBER')[-1]) == 1
    stock_list = sdk.getGlobal('stock_list')
    zz500_today = list(pd.Series(stock_list)[in_zz500_today])
    # 获取上一交易日中证500成分股
    zz500_yes = sdk.getGlobal('zz500_yes')
    # 找到新增成分股并为其建立仓位记录
    new_stock = sdk.getGlobal('new_stock')
    today_new_stock = list(set(zz500_today) - set(zz500_yes))
    if today_new_stock:
        for n in today_new_stock:
            position_of_stock[n] = {}
            position_of_stock[n]['cash'] = 0
            position_of_stock[n]['position'] = 0
    new_stock = new_stock + today_new_stock
    # 找到移出中证500的股票
    removed_stock = list(set(zz500_yes) - set(zz500_today))
    # 找到被移出中证500的有仓位和没仓位的股票
    stock_with_position = sdk.getGlobal('stock_with_position')
    if removed_stock:
        stock_with_position_today = [i for i in removed_stock if position_of_stock[i]['position'] > 0]
        stock_with_position.extend(stock_with_position_today)
        stock_with_no_position = list(set(removed_stock) - set(stock_with_position_today))
    else:
        stock_with_no_position = []
    sdk.setGlobal('stock_with_position', stock_with_position)
    # 将没有仓位的被移出的股票的现金分配给一部分新增股票
    if stock_with_no_position:
        for i in stock_with_no_position:
            temp = new_stock.pop(0)
            position_of_stock[temp]['cash'] = position_of_stock[i]['cash']
            position_of_stock[i]['cash'] = 0
    # 新增股票加入到了仓位信息中
    sdk.setGlobal('position_of_stock', position_of_stock)
    # 现在的new_stock是没有分到资金的新增股票
    sdk.setGlobal('new_stock', new_stock)
    # 以下代码获取当天未停牌未退市的股票，及可交易股票
    # not_stop = pd.isnull(sdk.getFieldData('LZ_GPA_SLCIND_STOP_FLAG')[-1])  # 当日没有停牌的股票
    not_stop = pd.isnull(sdk.getFieldData('LZ_GPA_SLCIND_STOP_FLAG')[-11:]).all(axis=0)  # 当日和前10日均没有停牌的股票
    on_list = list(pd.notnull(close.ix[today]))  # 存在于市场上的股票,去除退市股票
    zz500_not_stop = list(pd.Series(stock_list)[np.logical_and(np.logical_and(in_zz500_today, not_stop), on_list)])
    sdk.setGlobal('zz500_not_stop', zz500_not_stop)
    # 以下代码获取当天被移出中证500的有仓位的股票中可交易的股票
    not_stop_removed = list(
        set(pd.Series(stock_list)[np.logical_and(not_stop, on_list)]).intersection(set(stock_with_position)))
    sdk.setGlobal('not_stop_removed', not_stop_removed)
    # 订阅所有可交易的股票
    stock_observe = list(set(zz500_not_stop + not_stop_removed))
    sdk.subscribeQuote(stock_observe)
    # 找到所有可交易股票的收盘价,并计算MA和上轨
    close = pd.DataFrame(sdk.getFieldData('LZ_GPA_QUOTE_TCLOSE')[-10:], columns=stock_list)[stock_observe]
    mid_line = close.mean(axis=0)
    band_width = close.std(axis=0)
    up_line = mid_line + band_width * 2
    # 记录
    sdk.sdklog(today, '=======================================日期')
    sdk.sdklog(len(sdk.getPositions()), '持有股票数量')
    sdk.setGlobal('mid_line', mid_line)
    sdk.setGlobal('up_line', up_line)
    # 建立一个列表，来记录当天有过交易的股票
    traded_stock = []
    sdk.setGlobal('traded_stock', traded_stock)


def strategy(sdk):
    if (sdk.getNowTime() >= '093000') & (sdk.getNowTime() < '150000'):
        # today = sdk.getNowDate()
        # 每分钟开始时，加载今日已交易股票、上中轨
        traded_stock = sdk.getGlobal('traded_stock')
        up_line = sdk.getGlobal('up_line')
        mid_line = sdk.getGlobal('mid_line')
        # 加载移除股票有仓位的
        stock_with_position = sdk.getGlobal('stock_with_position')
        # 加载新增的未分配到资金的股票
        new_stock = sdk.getGlobal('new_stock')
        # 获取当天仓位信息
        position_of_stock = sdk.getGlobal('position_of_stock')
        # 获取被移出中证500的有仓位的股票中可交易的股票
        not_stop_removed = sdk.getGlobal('not_stop_removed')
        # 去除今天已经有交易的股票，获得当下还可交易的股票
        removed_stock_available = list(set(not_stop_removed) - set(traded_stock))
        # 获得中证500当日可交易的股票
        zz500_not_stop = sdk.getGlobal('zz500_not_stop')
        # 去除今天已经有交易的股票，获得当下还可交易的股票
        available_stock = list(set(zz500_not_stop) - set(traded_stock))
        # 取得盘口数据
        quotes = sdk.getQuotes(available_stock + removed_stock_available)

        # 考虑被移出中证500的那些股票
        sell_orders_removed = []
        if removed_stock_available:
            for stock_removed in removed_stock_available:
                cash_removed = position_of_stock[stock_removed]['cash']
                position_removed = position_of_stock[stock_removed]['position']
                current_price_removed = quotes[stock_removed].current
                mid_removed = mid_line[stock_removed]
                if current_price_removed < mid_removed:  # 判断是否卖出
                    order_removed = [stock_removed, current_price_removed, position_removed, -1]
                    sdk.makeOrders([order_removed])
                    sell_orders_removed.append(order_removed)
                    traded_stock.append(stock_removed)
                    # 计算仓位变化
                    cash_received_removed = position_removed * current_price_removed * (1 - Fee_Rate)
                    all_cash = cash_removed + cash_received_removed
                    position_of_stock[stock_removed]['cash'] = 0
                    position_of_stock[stock_removed]['position'] = 0
                    # 将卖出股票所有现金分配给一只新增的股票
                    temp = new_stock.pop(0)
                    position_of_stock[temp]['cash'] = all_cash
                    position_of_stock[temp]['position'] = 0
                    # 该只股票一经卖出，将其从stock_with_position列表中去除
                    stock_with_position.remove(stock_removed)
        # 考虑当日中证500可交易的股票
        buy_orders = []
        sell_orders = []
        for stock in available_stock:
            cash = position_of_stock[stock]['cash']
            position = position_of_stock[stock]['position']
            current_price = quotes[stock].current
            up = up_line[stock]
            mid = mid_line[stock]
            if (current_price > up) & (position == 0):
                volume = 100 * np.floor(cash / (100 * current_price))
                if volume > 0:
                    order = [stock, current_price, volume, 1]
                    buy_orders.append(order)
                    traded_stock.append(stock)  # 这里有待考虑，下单后不一定会成交,现假设都能成交
                    # 计算交易后的仓位变化，并记录在position_of_stock中
                    cash_payed = volume * current_price * (1 + Fee_Rate)
                    position_of_stock[stock]['cash'] = cash - cash_payed
                    position_of_stock[stock]['position'] = position + volume
                    # position_of_stock[stock]['last_trade_day'] = today
            elif (current_price < mid) & (position > 0):
                volume = position
                order = [stock, current_price, volume, -1]
                sell_orders.append(order)
                traded_stock.append(stock)
                # 计算交易后的仓位变化，并记录在position_of_stock中
                cash_received = volume * current_price * (1 - Fee_Rate)
                position_of_stock[stock]['cash'] = cash + cash_received
                position_of_stock[stock]['position'] = 0
                # position_of_stock[stock]['last_trade_day'] = today
            else:
                pass
        sdk.makeOrders(buy_orders)
        sdk.makeOrders(sell_orders)
        # 记录下单数据
        if buy_orders or sell_orders or sell_orders_removed:
            sdk.sdklog(sdk.getNowTime(), '=================时间')
            if buy_orders:
                sdk.sdklog('Buy orders')
                sdk.sdklog(np.array(buy_orders))
            if sell_orders:
                sdk.sdklog('Sell orders')
                sdk.sdklog(np.array(sell_orders))
            if sell_orders_removed:
                sdk.sdklog('Sell removed stocks')
                sdk.sdklog(np.array(sell_orders_removed))
        sdk.setGlobal('traded_stock', traded_stock)
        sdk.setGlobal('position_of_stock', position_of_stock)
        sdk.setGlobal('stock_with_position', stock_with_position)
        sdk.setGlobal('new_stock', new_stock)

config = {
    'username': username,
    'password': password,
    'initCapital': INIT_CAP,
    'startDate': START_DATE,
    'endDate': END_DATE,
    'strategy': strategy,
    'initial': initial,
    'preparePerDay': init_per_day,
    'feeRate': Fee_Rate,
    'strategyName': Strategy_Name,
    'logfile': '%s.log' % Strategy_Name,
    'rootpath': 'C:/cStrategy/',
    'executeMode': 'M',
    'feeLimit': 5,
    'cycle': 1,
    'playBackTime': 1,
    'allowfortodayfactor': ['LZ_GPA_INDEX_CSI500MEMBER', 'LZ_GPA_SLCIND_STOP_FLAG']
}

if __name__ == "__main__":
    # 在线运行所需代码
    import os
    config['strategyID'] = os.path.splitext(os.path.split(__file__)[1])[0]
    MiniSimulator(**config).run()
