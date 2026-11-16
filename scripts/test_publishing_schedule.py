"""Regression tests for the weekly Two Takes upload cadence."""

from publishing_schedule import short_publish_offsets


def test_tuesday_supplies_wednesday_and_friday():
    assert short_publish_offsets(1) == (1, 3)


def test_thursday_supplies_sunday():
    assert short_publish_offsets(3) == (3,)


def test_saturday_supplies_following_monday():
    assert short_publish_offsets(5) == (2,)


def test_no_shorts_are_allocated_to_non_long_video_days():
    for weekday in (0, 2, 4, 6):
        assert short_publish_offsets(weekday) == ()


def test_invalid_weekday_is_rejected():
    for weekday in (-1, 7, 1.5, "Tuesday"):
        try:
            short_publish_offsets(weekday)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected ValueError for {weekday!r}")


if __name__ == "__main__":
    test_tuesday_supplies_wednesday_and_friday()
    test_thursday_supplies_sunday()
    test_saturday_supplies_following_monday()
    test_no_shorts_are_allocated_to_non_long_video_days()
    test_invalid_weekday_is_rejected()
    print("Weekly publishing schedule tests passed.")
