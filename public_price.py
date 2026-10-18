import json
import math
from urllib.request import Request, urlopen
from urllib.parse import urlencode, urlparse
from urllib.error import HTTPError, URLError
import streamlit as st

st.set_page_config(page_title='실제 상품 가격 검색', page_icon='🛒', layout='wide')
st.title('🛒 실제 상품 가격 검색')
st.caption('SerpApi를 통해 Google Shopping의 실제 검색 결과를 가져옵니다. 수동 입력·가상 가격을 사용하지 않습니다.')
st.warning('검색된 후보 중 표시 최저가입니다. 동일 모델·옵션, 배송비, 쿠폰, 재고는 구매 페이지에서 확인하세요. 전체 시장 최저가나 최종 결제금액을 보장하지 않습니다.')
# 공개 서버에서는 Secrets에서 키를 읽고 방문자에게 표시하지 않습니다.
try:
    key = st.secrets.get('SERPAPI_API_KEY', '')
except FileNotFoundError:
    key = ''
if not key:
    with st.sidebar:
        st.info('로컬 테스트용 키 입력입니다. 공개 배포 시 Secrets를 설정하세요.')
        key = st.text_input('SerpApi API key', type='password')
import threading
import time
@st.cache_resource
def request_counter():
    return {'count': 0, 'lock': threading.Lock()}

with st.form('search'):
    query = st.text_input('원하는 상품명', placeholder='예: 로지텍 G304 블랙')
    excluded = st.text_input('제외할 단어 (쉼표로 구분)', placeholder='예: 케이스, 중고, 렌탈')
    submit = st.form_submit_button('실제 가격 검색')
if submit:
    st.session_state.pop('live_result', None)
    if not key.strip() or not query.strip():
        st.error('API 키와 상품명을 입력하세요.')
        st.stop()
    now = time.monotonic()
    if now - st.session_state.get('last_request', -100) < 15:
        st.warning('검색 사이에 15초 기다려 주세요.')
        st.stop()
    counter = request_counter()
    with counter['lock']:
        allowed = counter['count'] < 50
        if allowed:
            counter['count'] += 1
    if not allowed:
        st.warning('시연용 서버 검색 한도(50회)에 도달했습니다. 운영자에게 문의하세요.')
        st.stop()
    st.session_state.last_request = now
    url = 'https://serpapi.com/search.json?' + urlencode({'engine':'google_shopping','q':query.strip(),'gl':'kr','hl':'ko','api_key':key.strip()})
    try:
        with st.spinner('실제 쇼핑 검색 결과를 불러오는 중…'):
            with urlopen(Request(url), timeout=45) as response:
                data = json.load(response)
    except HTTPError as e:
        st.error(f'검색 요청 실패 (HTTP {e.code}). API 키, 계정 사용 한도와 서비스 상태를 확인하세요.')
        st.stop()
    except (URLError, TimeoutError, OSError, ValueError):
        st.error('네트워크 또는 응답 오류입니다. 잠시 후 다시 시도하세요.')
        st.stop()
    if not isinstance(data, dict) or data.get('error'):
        st.error('검색 서비스에서 결과를 반환하지 않았습니다. 계정 대시보드의 사용 상태를 확인하세요.')
        st.stop()
    words = [w.strip().casefold() for w in excluded.split(',') if w.strip()]
    rows = []
    for item in data.get('shopping_results', []):
        title = str(item.get('title', ''))
        if any(w in title.casefold() for w in words):
            continue
        price_text = str(item.get('price', ''))
        # 통화가 확인되지 않는 가격을 원화와 섞어 비교하지 않습니다.
        if not any(mark in price_text for mark in ('₩', '원', 'KRW')):
            continue
        try:
            amount = float(item.get('extracted_price'))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(amount) or amount <= 0:
            continue
        link = str(item.get('product_link') or item.get('link') or '')
        if urlparse(link).scheme not in ('http','https'):
            link = ''
        rows.append({'상품명':title,'판매처':str(item.get('source','')),'표시가격(원)':amount,'배송 안내':str(item.get('delivery','정보 없음')),'상품 링크':link})
    rows.sort(key=lambda r:r['표시가격(원)'])
    st.session_state.live_result = (query.strip(), rows)
if 'live_result' in st.session_state:
    searched, rows = st.session_state.live_result
    st.write('검색어:', searched)
    if not rows:
        st.info('검색 결과 중 원화 가격이 확인되는 후보가 없습니다. 정확한 모델명으로 다시 검색하세요. 상품과 지역에 따라 결과가 없을 수 있습니다.')
    else:
        a,b = st.columns(2)
        a.metric('가져온 결과 중 최저 표시가격', f"{rows[0]['표시가격(원)']:,.0f}원")
        b.metric('비교 후보 수', len(rows))
        st.subheader(rows[0]['상품명'])
        st.write('판매처:',rows[0]['판매처'])
        if rows[0]['상품 링크']:
            st.link_button('최저가 후보 확인', rows[0]['상품 링크'])
        st.dataframe(rows,hide_index=True,column_config={'상품 링크':st.column_config.LinkColumn(display_text='상품 확인')})
        st.caption('첫 검색 응답의 원화 상품만 비교합니다. 검색 공급자가 캐시한 결과일 수 있으며 실제 결제 시점 가격과 다를 수 있습니다.')
