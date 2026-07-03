from intent_engine.core.pipeline import Stage


def test_stage_is_abstract_and_requires_run():
    class Incomplete(Stage):
        pass

    try:
        Incomplete()
    except TypeError:
        pass
    else:
        raise AssertionError("Stage subclasses without run() should not be instantiable")


def test_stage_subclass_with_run_is_usable():
    class Echo(Stage):
        name = "echo"

        def run(self, value):
            return value

    stage = Echo()
    assert stage.run("hello") == "hello"
