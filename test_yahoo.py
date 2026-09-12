import unittest
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
from market import demo, scan
from yahoo import normalize_symbols,fetch_universe,quality_universe
from yahoo_download import download_universe
from streamlit.testing.v1 import AppTest

class YahooTests(unittest.TestCase):
    def frame(self):
        d=demo().iloc[:100].drop(columns='symbol').copy()
        today=pd.Timestamp(datetime.now(ZoneInfo('Asia/Jakarta')).date())
        d['date']=pd.bdate_range(end=today-pd.Timedelta(days=1),periods=100)
        d=d.set_index('date');d.index.name='Date';d.columns=d.columns.str.title()
        return d
    def batch(self,syms,field_first=True):
        d=pd.concat({s:self.frame() for s in syms},axis=1)
        return d.swaplevel(axis=1) if field_first else d
    def test_symbols_and_universe(self):
        self.assertEqual(normalize_symbols('bbca, BBCA.JK; ISAT'),('BBCA','ISAT'))
        self.assertEqual(len(set(quality_universe())),200)
        with self.assertRaises(ValueError): normalize_symbols('$BAD')
    def test_200_batch_processing(self):
        def mocked(*args,**kw): return self.batch(kw['tickers'])
        with patch('yahoo_download.yf.download',side_effect=mocked) as fetch:
            p,r,t=fetch_universe(quality_universe())
            self.assertEqual(len(r),200);self.assertEqual(p.symbol.nunique(),200)
            self.assertTrue(r.Status.eq('OK').all());self.assertEqual(fetch.call_count,4)
            self.assertEqual([len(c.kwargs['tickers']) for c in fetch.call_args_list],[60,60,60,20])
            self.assertFalse(fetch.call_args.kwargs['auto_adjust'])
            self.assertEqual(len(scan(p)),200)
    def test_recovery_multiindex(self):
        for orientation in (True,False):
            with patch('yahoo_download.yf.download',side_effect=[self.batch(['BBCA.JK'],orientation),self.frame()]) as fetch:
                p,r,t=fetch_universe(('BBCA','ISAT'))
                self.assertTrue(r.Status.eq('OK').all());self.assertEqual(fetch.call_count,2)
                self.assertEqual(fetch.call_args.args[0],'ISAT.JK')
    def test_failure_stale_today(self):
        old=self.frame();old.index-=pd.Timedelta(days=60)
        today=pd.Timestamp(datetime.now(ZoneInfo('Asia/Jakarta')).date())
        current=self.frame();current.loc[today]=current.iloc[-1]
        with patch('yahoo_download.download_universe',return_value=({'BBCA.JK':current,'OLDX.JK':old},{'FAIL.JK':'rate limited'})):
            p,r,t=fetch_universe(('BBCA','FAIL','OLDX'))
            self.assertEqual(list(r.Status),['OK','Failed','Stale — excluded'])
            self.assertTrue((p.date.dt.date<today.date()).all())
        with patch('yahoo_download.download_universe',return_value=({}, {'FAIL.JK':'empty'})):
            p,r,t=fetch_universe(('FAIL',));self.assertTrue(p.empty)
    def test_yahoo_ui(self):
        def mocked(*args,**kw): return self.batch(kw['tickers'])
        with patch('yahoo_download.yf.download',side_effect=mocked):
            at=AppTest.from_file('app.py',default_timeout=60).run()
            next(b for b in at.button if b.label=='Fetch & scan').click().run()
            self.assertEqual(len(at.exception),0)
            self.assertEqual(len(at.session_state['yahoo_bundle'][1]),200)

if __name__=='__main__': unittest.main()
