import os
import sys


def test_rampuptime_good_readme():
    m = RampUpTime.RampUpTime()
    readme_text = """
    # Example Model
    ## Installation
    pip install example-model
    ## Usage
    from example import run
    run()
    """
    m.setRampUpTime(readme_text=readme_text)
    score = m.getRampUpTime()
    print("Good README score:", score)
    assert 0.0 <= score <= 1.0


def test_rampuptime_bad_readme():
    m = RampUpTime.RampUpTime()
    m.setRampUpTime(readme_text="Just a title, no details")
    score = m.getRampUpTime()
    print("Bad README score:", score)
    assert 0.0 <= score <= 1.0


def test_rampuptime_precomputed():
    m = RampUpTime.RampUpTime()
    m.setRampUpTime(precomputed_score=0.5)
    score = m.getRampUpTime()
    print("Precomputed score:", score)
    assert score == 0.5