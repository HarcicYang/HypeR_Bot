n = int(input())
lis: list[int] = []


for i in range(n):
    lis.append(int(input()))

print(lis)
print(max(*lis))
print(min(*lis))
