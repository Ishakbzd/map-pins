from dataclasses import dataclass, field
from typing import List


@dataclass
class Package:
    code: str
    tracking_id: str
    seq: int
    street: str
    city: str
    province: str
    postal_code: str
    dimensions: str
    full_address: str


@dataclass
class Route:
    code: str
    date: str
    packages: List[Package] = field(default_factory=list)

    @property
    def total_packages(self) -> int:
        return len(self.packages)

    @property
    def city(self) -> str:
        if not self.packages:
            return ""
        return self.packages[0].city
