def decorator(func):
    def wrapper(x,y):
        print('Before function call')
        print(f"The first value is {x}\n and the second is {y}")
        print('After function call')
        return func(x,y)
    return wrapper

@decorator
def add(a, b):
    return a + b

def main():
    print('This program is being run by another module')
    results = add(10,23)
    print(f"The result is {results}")

if __name__ == '__main__':
    print('This program is being run by itself')
    main()
    print(add(1, 2))