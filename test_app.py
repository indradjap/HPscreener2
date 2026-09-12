import unittest
import numpy as np
from streamlit.testing.v1 import AppTest
from market import demo, parse_csv, indicators, scan, position_size

class MarketTests(unittest.TestCase):
    def test_import(self):
        d=demo(); self.assertEqual(len(parse_csv(d.to_csv(index=False).encode())),len(d))
        for bad in [d.iloc[:5], __import__('pandas').concat([d,d.iloc[:1]],ignore_index=True)]:
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
    def test_tools_without_prices(self):
        at=AppTest.from_file('app.py',default_timeout=30).run()
        for page in ['Risk Calculator','Average Price','HP Desk','Trading Journal','Stock Universe','Saved Screens']:
            at.button(key='nav_'+page).click().run()
            self.assertEqual(len(at.exception),0,page)
            self.assertEqual(at.title[0].value,page)
        self.assertTrue(any('No saved screens' in i.value for i in at.info))
    def test_saved_screen_navigation(self):
        at=AppTest.from_file('app.py',default_timeout=30).run()
        at.selectbox(key='price_source').set_value('Demo').run()
        at.button(key='nav_Technical Screener').click().run()
        next(t for t in at.text_input if t.label=='Save these conditions as').set_value('My trend')
        next(b for b in at.button if b.label=='Save screen').click().run()
        at.button(key='nav_Saved Screens').click().run()
        at.button(key='open_My trend').click().run()
        self.assertEqual(at.selectbox(key='preset_select').value,'Saved: My trend')
        self.assertEqual(len(at.exception),0)
    def test_pages(self):
        at=AppTest.from_file('app.py',default_timeout=30).run()
        self.assertEqual(len(at.exception),0)
        at.selectbox[0].set_value('Demo').run()
        for page in ['Market Overview','Stock Charts','Technical Screener','Watchlist','HP Desk','Stock Universe','Top Movers','Leaders & Laggards','Volume Activity','HP Metrics','Saved Screens','Trading Journal','Risk Calculator','Average Price']:
            at.button(key='nav_'+page).click().run()
            self.assertEqual(len(at.exception),0, page)
        at.button(key='nav_Technical Screener').click().run()
        at.selectbox(key='preset_select').set_value('Trend + volume').run()
        self.assertEqual(len(at.exception),0)
        at.button(key='nav_HP Desk').click().run()
        at.text_area[0].set_value('Test thesis')
        next(b for b in at.button if b.label=='Save note').click().run()
        self.assertIn('Test thesis',at.session_state['notes'].values())
        at.button(key='nav_Trading Journal').click().run()
        next(b for b in at.button if b.label=='Record closed trade').click().run()
        self.assertEqual(len(at.session_state['journal']),1)
        self.assertEqual(len(at.exception),0)

if __name__=='__main__': unittest.main()
