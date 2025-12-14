#include "kinematics.h"
#include "config.h"
#include <math.h>

namespace Kinematics {

Angles inverse(float x, float y, float z) {
    Angles result = {0, 0, 0, false};

    // 1. Base Angle
    result.base = degrees(atan2(y, x));

    // 2. Reach (Planar Projection)
    float r = sqrt(x*x + y*y);

    // 3. Triangle Solution
    // Distance from Shoulder Pivot (0,0,0 local) to Target (r, z)
    float c_sq = r*r + z*z;
    float c = sqrt(c_sq);

    // Reachability Check
    if (c > (GEO_L1 + GEO_L2)) {
        result.reachable = false;
        return result;
    }

    // Law of Cosines for Shoulder (Alpha 1)
    // L2^2 = L1^2 + c^2 - 2*L1*c*cos(a1)
    float cos_a1 = (GEO_L1*GEO_L1 + c_sq - GEO_L2*GEO_L2) / (2 * GEO_L1 * c);
    cos_a1 = constrain(cos_a1, -1.0f, 1.0f);
    float a1 = acos(cos_a1);

    // Elevation of Target (Alpha 2)
    float a2 = atan2(z, r);

    // Shoulder Angle
    result.shoulder = degrees(a1 + a2);

    // Law of Cosines for Elbow (Gamma Internal)
    // c^2 = L1^2 + L2^2 - 2*L1*L2*cos(gamma)
    float cos_gamma = (GEO_L1*GEO_L1 + GEO_L2*GEO_L2 - c_sq) / (2 * GEO_L1 * GEO_L2);
    cos_gamma = constrain(cos_gamma, -1.0f, 1.0f);
    float gamma = acos(cos_gamma);

    // Elbow Angle (Geometry Dependent)
    // Returning Internal Angle typically
    result.elbow = degrees(gamma);

    result.reachable = true;
    return result;
}

}
