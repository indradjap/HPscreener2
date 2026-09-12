import unittest
import numpy as np
from streamlit.testing.v1 import AppTest
from market import demo, parse_csv, indicators, scan, position_size

class MarketTests(unittest.TestCase):
    def test_import(self):
        d=demo(); self.assertEqual(len(parse_csv(d.to_csv(index=False).encode())),len(d))
        for bad in [d.iloc[:5], d._append(d.iloc[:1])]:
            with self.assertRaises(ValueError): parse_csv(bad.to_csv(index=False).encode())
        d.loc[0,'high']=1
        with self.assertRaises(ValueError): parse_csv(d.to_csv(index=False).encode())
    def test_calculations(self):
        d=demo().iloc[:100].copy(); d['close']=np.arange(1.,101.); d['volume']=100
        x=indicators(d).iloc[-1]
        self.assertEqual(x.MA20,90.5); self.assertEqual(x.RSI,100); self.assertEqual(x.RelVolume,1)
        self.assertEqual(position_size(10000000,1,1000,950),(20,2000000,100000))
        with self.assertRaises(ValueError): position_size(1000,1,100,100)
        self.assertEqual(len(scan(demo())),18)
    def test_pages(self):
        at=AppTest.from_file('app.py',default_timeout=30).run()
        self.assertEqual(len(at.exception),0)
        for page in ['Market Overview','Stock Charts','Screener','Watchlist','Research Notes','Trading Journal','Calculators']:
            at.sidebar.radio[0].set_value(page).run()
            self.assertEqual(len(at.exception),0, page)
        at.sidebar.radio[0].set_value('Screener').run()
        at.selectbox[0].set_value('Trend + volume').run()
        self.assertEqual(len(at.exception),0)
        at.sidebar.radio[0].set_value('Research Notes').run()
        at.text_area[0].set_value('Test thesis')
        next(b for b in at.button if b.label=='Save note').click().run()
        self.assertIn('Test thesis',at.session_state['notes'].values())
        at.sidebar.radio[0].set_value('Trading Journal').run()
        next(b for b in at.button if b.label=='Record closed trade').click().run()
        self.assertEqual(len(at.session_state['journal']),1)
        self.assertEqual(len(at.exception),0)

if __name__=='__main__': unittest.main()
