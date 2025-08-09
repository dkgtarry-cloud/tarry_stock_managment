import streamlit as st
import pandas as pd
import requests
import json
import os
from datetime import datetime
import akshare as ak

# 页面配置
st.set_page_config(
    page_title="资产管理系统",
    page_icon="📈",
    layout="wide"
)

# 数据持久化
DATA_FILE = "portfolio_data.json"


def load_portfolio():
    """加载持仓数据并进行数据迁移（添加缺失的字段）"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            portfolio = json.load(f)

            # 数据迁移：添加缺失的字段（向后兼容）
            for item in portfolio:
                item.setdefault('type', "股票")
                item.setdefault('currency', 'HKD' if item['market'] == '港股' else 'CNY')

            return portfolio
    return []


def save_portfolio(portfolio):
    """保存持仓数据"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(portfolio, f, ensure_ascii=False, indent=2)


# 缓存汇率数据（每小时更新）
@st.cache_data(ttl=3600)
def get_hkd_to_cny_rate():
    """获取港币兑人民币汇率"""
    try:
        url = "https://api.exchangerate-api.com/v4/latest/HKD"
        response = requests.get(url, timeout=5)
        data = response.json()
        return data["rates"]["CNY"]
    except:
        return 0.92  # 默认汇率


# 缓存股票数据（降低API调用频率）
@st.cache_data(ttl=300)  # 5分钟缓存
def get_stock_info(symbol, market):
    """获取股票实时信息"""
    try:
        symbol = str(symbol).strip()
        if market == "A股":
            symbol_str = symbol.zfill(6)
            df = ak.stock_individual_info_em(symbol=symbol_str)
            info_dict = df.set_index('item')['value'].to_dict()

            return {
                'name': info_dict.get('股票简称', f"股票 {symbol_str}"),
                'current_price': float(info_dict.get('最新', 0)),
                'currency': 'CNY'
            }
        else:  # 港股
            df = ak.stock_hk_spot_em()
            stock_row = df[df['代码'].astype(str) == symbol.zfill(5)]

            if not stock_row.empty:
                return {
                    'name': stock_row['名称'].values[0],
                    'current_price': stock_row['最新价'].values[0],
                    'currency': 'HKD'
                }
            return {
                'name': f"港股 {symbol}",
                'current_price': 0,
                'currency': 'HKD'
            }
    except Exception as e:
        st.error(f"获取股票 {symbol} 信息失败: {str(e)}")
        return {
            'name': symbol,
            'current_price': 0,
            'currency': 'HKD' if market == '港股' else 'CNY'
        }


# 缓存ETF数据（使用新的API接口）
@st.cache_data(ttl=300)  # 5分钟缓存
def get_etf_info(symbol):
    """获取ETF基金实时信息（使用新的API接口）"""
    try:
        symbol = str(symbol).strip().zfill(6)
        etf_df = ak.fund_etf_spot_em()

        # 查找匹配的基金代码
        etf_row = etf_df[etf_df['代码'].astype(str) == symbol]

        if not etf_row.empty:
            name = etf_row['名称'].values[0]
            current_price = etf_row['最新价'].values[0]
            # 确保价格是数值类型
            current_price = float(current_price) if isinstance(current_price, (int, float)) else 0.0
            return {
                'name': name,
                'current_price': round(current_price, 3),
                'currency': 'CNY'
            }
        return {
            'name': f"ETF基金 {symbol}",
            'current_price': 0.0,
            'currency': 'CNY'
        }
    except Exception as e:
        st.error(f"获取ETF基金 {symbol} 信息失败: {str(e)}")
        return {
            'name': f"ETF基金 {symbol}",
            'current_price': 0.0,
            'currency': 'CNY'
        }


def calculate_return(cost_price, current_price):
    """计算收益率"""
    if cost_price == 0:
        return 0
    return ((current_price - cost_price) / cost_price) * 100


# 主界面
def main():
    st.title("资产管理系统")

    # 初始化session state
    if 'portfolio' not in st.session_state:
        st.session_state.portfolio = load_portfolio()
    if 'last_update' not in st.session_state:
        st.session_state.last_update = datetime.now()

    # 侧边栏 - 添加资产
    with st.sidebar:
        st.header("添加资产")
        with st.form("add_asset_form"):
            asset_type = st.selectbox("资产类型", ["股票", "ETF基金"])

            if asset_type == "股票":
                symbol = st.text_input("股票代码", placeholder="如: 000001 或 00700")
                market = st.selectbox("市场类型", ["A股", "港股"])
            else:  # ETF基金
                symbol = st.text_input("基金代码", placeholder="如: 159691")
                market = "A股"  # ETF基金默认为A股市场

            shares = st.number_input("持有份额", min_value=0, step=100)
            cost_price = st.number_input("成本价", min_value=0.0, step=0.01, format="%.6f")

            submitted = st.form_submit_button("添加")

            if submitted and symbol and shares > 0 and cost_price > 0:
                asset_info = get_etf_info(symbol) if asset_type == "ETF基金" else get_stock_info(symbol, market)

                new_asset = {
                    'symbol': symbol,
                    'type': asset_type,
                    'market': market,
                    'shares': shares,
                    'cost_price': round(cost_price, 3) if asset_type == "ETF基金" else cost_price,
                    'name': asset_info['name'],
                    'current_price': asset_info['current_price'],
                    'currency': asset_info['currency']
                }

                st.session_state.portfolio.append(new_asset)
                save_portfolio(st.session_state.portfolio)
                st.success("资产添加成功！")
                st.rerun()
            elif submitted:
                st.error("请填写完整信息！")

        # 删除资产功能
        st.subheader("管理持仓")
        if st.session_state.portfolio:
            selected_asset = st.selectbox(
                "选择要删除的资产",
                options=range(len(st.session_state.portfolio)),
                format_func=lambda x: (
                    f"{st.session_state.portfolio[x]['name']} "
                    f"({st.session_state.portfolio[x]['symbol']})"
                )
            )

            if st.button("删除选中资产", type="secondary"):
                del st.session_state.portfolio[selected_asset]
                save_portfolio(st.session_state.portfolio)
                st.success("资产删除成功！")
                st.rerun()

    # 主内容区
    if not st.session_state.portfolio:
        st.info("暂无持仓，请在左侧添加资产")
        return

    # 刷新区
    col1, col2 = st.columns([4, 1])
    with col1:
        st.caption(f"最后更新时间: {st.session_state.last_update.strftime('%Y-%m-%d %H:%M:%S')}")
    with col2:
        if st.button("刷新数据", width=115):
            with st.spinner("正在更新数据..."):
                hkd_to_cny = get_hkd_to_cny_rate()
                updated = False

                for asset in st.session_state.portfolio:
                    try:
                        if asset['type'] == "股票":
                            asset_info = get_stock_info(asset['symbol'], asset['market'])
                        else:
                            asset_info = get_etf_info(asset['symbol'])

                        # 更新价格和名称
                        new_price = round(asset_info['current_price'], 3) if asset['type'] == "ETF基金" else asset_info[
                            'current_price']
                        if asset['current_price'] != new_price:
                            asset['current_price'] = new_price
                            updated = True

                        if asset_info['name'] != asset['name']:
                            asset['name'] = asset_info['name']
                            updated = True
                    except Exception as e:
                        st.error(f"更新资产 {asset['symbol']} 信息失败: {str(e)}")

                if updated:
                    st.session_state.last_update = datetime.now()
                    save_portfolio(st.session_state.portfolio)
                    st.success("数据更新成功！")
                else:
                    st.info("数据无变化")
                st.rerun()

    # 准备显示数据
    display_data = []
    total_assets = total_investment = total_profit = 0
    hkd_to_cny = get_hkd_to_cny_rate()

    for asset in st.session_state.portfolio:
        # 确保字段存在
        asset.setdefault('type', "股票")
        asset.setdefault('currency', 'CNY')

        # 计算资产价值
        market_value = asset['shares'] * asset['current_price']
        cost_value = asset['shares'] * asset['cost_price']
        return_rate = calculate_return(asset['cost_price'], asset['current_price'])
        profit = market_value - cost_value

        # 转换为人民币
        if asset['currency'] == 'HKD':
            market_value_cny = market_value * hkd_to_cny
            cost_value_cny = cost_value * hkd_to_cny
            profit_cny = profit * hkd_to_cny
        else:
            market_value_cny = market_value
            cost_value_cny = cost_value
            profit_cny = profit

        total_assets += market_value_cny
        total_investment += cost_value_cny
        total_profit += profit_cny

        # 直接构建格式化后的行
        display_data.append({
            '资产类型': asset['type'],
            '名称': asset['name'],
            '代码': asset['symbol'],
            '市场': asset['market'],
            '持有份额': f"{asset['shares']:,}",
            '成本价': f"¥{asset['cost_price']:.3f}" if asset['type'] == 'ETF基金' else f"¥{asset['cost_price']:.2f}",
            '最新价': f"¥{asset['current_price']:.3f}" if asset[
                                                              'type'] == 'ETF基金' else f"¥{asset['current_price']:.2f}",
            '收益率': f"{return_rate:.2f}%",
            '持仓市值': f"¥{market_value_cny:,.2f}",
            '盈亏金额': f"¥{profit_cny:+,.2f}" if profit_cny != 0 else "¥0.00"
        })

    # 显示表格
    st.subheader("持仓明细")
    df = pd.DataFrame(display_data)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_order=['资产类型', '名称', '代码', '市场', '持有份额', '成本价', '最新价', '收益率', '持仓市值',
                      '盈亏金额']
    )

    # 显示总资产和总收益
    col1, col2 = st.columns(2)
    col1.metric(
        "总收益（人民币）",
        f"¥{total_profit:,.2f}",
        f"{(total_profit / total_investment * 100 if total_investment > 0 else 0):.2f}%"
    )
    col2.metric(
        "总资产（人民币）",
        f"¥{total_assets:,.2f}",
        f"¥{total_profit:+,.2f}"
    )


if __name__ == "__main__":
    main()