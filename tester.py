import json
import pprint

with open("quick.json", "r", encoding="utf-8") as f:
    test = json.load(f)
pprint.pprint(test)
for i in test["group_increase"]:
    o_i = i
    for j in i:
        # 判断字符是否为汉字
        if '\u4e00' <= j <= '\u9fff':
            # 如果是，则替换为下划线
            i = i.replace(j, "_", 1)
        else:
            pass
    test["group_increase"][test["group_increase"].index(o_i)] = i

with open("quick2.json", "w", encoding="utf-8") as f:
    json.dump(test, f, ensure_ascii=False, indent=2)
