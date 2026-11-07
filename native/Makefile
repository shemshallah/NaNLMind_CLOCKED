CC ?= cc
CFLAGS ?= -std=c99 -O2 -Wall -Wextra -Wpedantic -Werror
TARGET = build/test_clocked_nan

all: $(TARGET)

$(TARGET): clocked_nan.c test_clocked_nan.c clocked_nan.h
	mkdir -p build
	$(CC) $(CFLAGS) -I. clocked_nan.c test_clocked_nan.c -o $(TARGET)

test: $(TARGET)
	./$(TARGET)

clean:
	rm -rf build
