"""
This file is part of Systolic.
Systolic is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Systolic is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with Systolic.  If not, see https://www.gnu.org/licenses/.
"""

import numpy as np


def mean_downscaler(data, n):
    n = int(n)
    mod = len(data) % n
    data = np.resize(data, (data.size+(n-mod)))
    if mod != 0:
        for _ in np.arange(mod):
            np.append(data, None)
    meanArr = []
    finalArr = []
    for i in data:
        meanArr.append(i)
        if len(meanArr) == n:
            finalArr.append(np.mean(meanArr))
            meanArr = []
        else:
            continue
    return finalArr
