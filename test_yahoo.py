import unittest
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
from market import demo
from yahoo import normalize_symbols,fetch_one,fetch_universe
from streamlit.testing.v1 import AppTest

class YahooTests(unittest.TestCase):
    def fixture(self,s):
        d=demo().iloc[:100].copy();d['symbol']=s
        today=pd.Timestamp(datetime.now(ZoneInfo('Asia/Jakarta')).date())
        d['date']=pd.bdate_range(end=today-pd.Timedelta(days=1),periods=100)
        return d
    def test_symbols(self):
        self.assertEqual(normalize_symbols('bbca, BBCA.JK; ISAT'),('BBCA','ISAT'))
        with self.assertRaises(ValueError): normalize_symbols('BBCA, $BAD')
    def test_partial(self):
        def loader(s,*args):
            if s=='FAIL': raise ValueError('Provider unavailable')
            d=self.fixture(s)
            if s=='OLDX': d['date']-=pd.Timedelta(days=60)
            return d
        p,r,t=fetch_universe(('BBCA','FAIL','OLDX'),loader=loader)
        self.assertEqual(set(p.symbol),{'BBCA'})
        self.assertEqual(list(r.Status),['OK','Failed','Stale — excluded'])
    def test_normalization_and_today(self):
        d=self.fixture('BBCA').drop(columns='symbol').set_index('date')
        d.index.name='Date';d.columns=d.columns.str.title()
        with patch('yahoo.yf.Ticker') as ticker:
            ticker.return_value.history.return_value=d
            p=fetch_one('BBCA')
            self.assertEqual(len(p),100)
            self.assertEqual(set(p.symbol),{'BBCA'})
            self.assertTrue(ticker.return_value.history.call_args.kwargs['auto_adjust'])
    def test_yahoo_ui(self):
        with patch('yahoo.fetch_one',side_effect=lambda s,*a:self.fixture(s)):
            at=AppTest.from_file('app.py',default_timeout=30).run()
            next(b for b in at.button if b.label=='Fetch & scan').click().run()
            self.assertEqual(len(at.exception),0)
            self.assertEqual(len(at.session_state['yahoo_bundle'][1]),18)

if __name__=='__main__': unittest.main()
