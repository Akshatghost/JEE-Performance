from app import pct, moving, consistency
def test_pct(): assert pct(5,10)==50
def test_moving(): assert moving([10,20,30],2)==25
def test_consistency(): assert consistency([10,10,10])==100
