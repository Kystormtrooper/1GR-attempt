from glove.api import GestureAPI
from glove.hw_stub import StubGlove

glove = GestureAPI(StubGlove())
print(glove.connect())

for i in range(3):
    glove.pump()
    ok, msg, st = glove.status()
    print(msg, st.last_reading)