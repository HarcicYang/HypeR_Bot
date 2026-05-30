from lief import parse
from capstone import Cs, CS_ARCH_X86, CS_MODE_64


# path = "/opt/QQ/resources/app/wrapper.node"
path = "./30366/wrapper.node"

with open(path, "rb") as f:
    data = f.read()

binary = parse(path)
md = Cs(CS_ARCH_X86, CS_MODE_64)
for sym in binary.symbols:
    # if sym.value != 0x5324025:
    #     continue
    print(f"{sym.name} @ 0x{sym.value}")
    # for i in md.disasm(data[0x123456:0x123456 + 0x100], eval(f"0x{sym.value}")):
    #     print(f"0x{i.address:x}:\t{i.mnemonic}\t{i.op_str}")

for i in md.disasm(data, eval(f"0x{5324025}")):
    print(f"0x{i.address:x}:\t{i.mnemonic}\t{i.op_str}")