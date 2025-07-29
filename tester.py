import sys

from PIL import Image


class CodeImageLine:
    def __init__(self, length: int):
        self.length = length
        self.data = [(0, 0, 0, 0) for _ in range(length)]

    def set(self, index: int, rgba: tuple[int, int, int, int]) -> None:
        self.data[index] = rgba

    def get(self, index: int) -> tuple[int, int, int, int]:
        return self.data[index]

    def out(self) -> list[tuple[int, int, int, int]]:
        return self.data


class CodeImage:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.data = [CodeImageLine(width) for _ in range(height)]

    def set(self, lindex: int, hindex: int, rgba: tuple[int, int, int, int]) -> None:
        self.data[hindex].set(lindex, rgba)

    def get(self, lindex: int, hindex: int) -> tuple[int, int, int, int]:
        return self.data[hindex].get(lindex)

    def gen(self) -> Image.Image:
        img = Image.new("RGBA", (self.width, self.height))
        pixels = img.load()
        for x in range(self.width):
            for y in range(self.height):
                pixels[x, y] = self.get(x, y)
        return img

    def tout(self) -> list[list[tuple[int, int, int, int]]]:
        return [i_.out() for i_ in self.data]

    @classmethod
    def tin(cls, data: list[list[tuple[int, int, int, int]]]) -> "CodeImage":
        height = len(data)
        width = len(data[0])
        new = CodeImage(width, height)
        for x in range(width):
            for y in range(height):
                new.set(x, y, data[y][x])
        return new

    @classmethod
    def load(cls, path: str) -> "CodeImage":
        img = Image.open(path).convert("RGBA")
        pixels = img.load()
        new = cls(img.width, img.height)
        for x in range(img.width):
            for y in range(img.height):
                new.set(x, y, pixels[x, y])

        return new


# my_img = CodeImage(16, 16)

# my_img.gen().show()
# my_img = CodeImage.load("./logo.ico")
# for i in range(256):
#     my_img.set(i, i, (255, 255, 255, int(255 * i / 265)))
# my_img.gen().show()

my_img = CodeImage.tin(

)
my_img.gen().show()
"""
现在，你是一个图片生成机器人，任何图片的输入和输出遵循“listimg”标准。我们如下定义listimg标准：
该标准用python3标准中的列表（list[list[tuple[int, int, int, int]]]）为行和列的储存，每个像素点使用rgba格式表示，储存为python3标准中的元组（tuple[int, int, int, int]）。
示例：
[
    [(255, 255, 255, 255), (0, 0, 0, 0), (255, 255, 255, 255)],
    [(0, 0, 0, 0), (255, 255, 255, 255), (0, 0, 0, 0)],
    [(255, 255, 255, 255), (0, 0, 0, 0), (255, 255, 255, 255)]
]
是一个合法的listimg标准图片，他表示一个3*3大小的图片。
"""