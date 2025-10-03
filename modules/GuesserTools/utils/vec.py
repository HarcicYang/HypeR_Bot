from typing import Union
import numpy as np


class Vector:
    def __init__(self, *args: Union[int, float], dim: int = 3):
        self.data = np.array(args, dtype=np.float64)
        self.dim = dim
        if len(self.data) != self.dim:
            raise ValueError(f"Vector dimension must be {self.dim}, got {len(self.data)}")

    def __add__(self, other: "Vector") -> "Vector":
        if other.dim != self.dim:
            raise ValueError(f"Vector dimension must be the same, got {self.dim} and {other.dim}")
        return Vector(*(self.data + other.data), dim=self.dim)

    def __sub__(self, other: "Vector") -> "Vector":
        if other.dim != self.dim:
            raise ValueError(f"Vector dimension must be the same, got {self.dim} and {other.dim}")
        return Vector(*(self.data - other.data), dim=self.dim)

    def __mul__(self, other: "Vector") -> Union[int, float]:
        if other.dim != self.dim:
            raise ValueError(f"Vector dimension must be the same, got {self.dim} and {other.dim}")
        return float(np.dot(self.data, other.data))

    def __rmul__(self, scalar: Union[int, float]) -> "Vector":
        return Vector(*(self.data * scalar), dim=self.dim)

    def __truediv__(self, scalar: Union[int, float]) -> "Vector":
        return Vector(*(self.data / scalar), dim=self.dim)

    def __repr__(self) -> str:
        return f"({', '.join(map(str, self.data))})"

    def __len__(self) -> int:
        return self.dim

    def __getitem__(self, key: int) -> Union[int, float]:
        return float(self.data[key])

    @property
    def mod(self) -> Union[int, float]:
        return float(np.linalg.norm(self.data))


def distance(v1: Vector, v2: Vector) -> float:
    if v1.dim != v2.dim:
        raise ValueError(f"Vector dimension must be the same, got {v1.dim} and {v2.dim}")
    return float(np.linalg.norm(v1.data - v2.data))
