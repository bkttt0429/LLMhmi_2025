#ifndef KINEMATICS_H
#define KINEMATICS_H

struct Angles {
    float base;
    float shoulder;
    float elbow;
    bool reachable;
};

namespace Kinematics {
    Angles inverse(float x, float y, float z);
};

#endif
