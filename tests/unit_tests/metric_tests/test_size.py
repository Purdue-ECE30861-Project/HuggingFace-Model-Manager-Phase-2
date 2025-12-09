import sys, os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.backend_server.classes.size import Size


def test_size_small_project():
    m = Size()
    m.setSize([500 * 1024 * 1024])  
    score = m.getSize()
    size_gb = m.getModelSizeGB()
    print("Small project size (GB):", size_gb, "score:", score)
    assert score == 1.0
    assert size_gb < 1.0


def test_size_large_project():
    m = Size()
    m.setSize([5 * 1024 * 1024 * 1024])  
    score = m.getSize()
    size_gb = m.getModelSizeGB()
    print("Large project size (GB):", size_gb, "score:", score)
    assert score == 0.5
    assert 1.0 <= size_gb < 10.0


def test_size_huge_project():
    m = Size()
    m.setSize([20 * 1024 * 1024 * 1024])  
    score = m.getSize()
    size_gb = m.getModelSizeGB()
    print("Huge project size (GB):", size_gb, "score:", score)
    assert score == 0.0
    assert size_gb >= 10.0