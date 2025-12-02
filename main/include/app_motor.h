#ifndef APP_MOTOR_H
#define APP_MOTOR_H

#include <stdint.h>

void app_motor_init(void);
void app_motor_set_pwm(int left_val, int right_val);

#endif
