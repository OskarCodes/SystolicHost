"""
This file just contains a useful function I made for downscaling data

Copyright 2020 OskarCodes

This file is part of Systolic

Systolic is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Systolic is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Systolic.  If not, see <https://www.gnu.org/licenses/>.
"""

import numpy as np
import matplotlib.pyplot as plt


def mean_downscaler(data, n):
    n = int(n)
    mod = len(data) % n
    # Resize array to allow for division with requested downscale factor
    data = np.resize(data, (data.size+(n-mod)))
    if mod != 0:
        for _ in np.arange(mod):
            # This is probably not needed at all, but adds "None"s to empty spots
            np.append(data, None)
    # Constructs arrays
    meanArr = []
    finalArr = []
    for i in data:
        # Add value to temp array
        meanArr.append(i)
        if len(meanArr) == n:
            # Once temp array is of desired length, calculate mean and add to final
            finalArr.append(np.mean(meanArr))
            # Reset temporary array
            meanArr = []
        else:
            continue
    # Return final array
    return finalArr
