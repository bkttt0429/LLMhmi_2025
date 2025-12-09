#ifndef APP_MOTOR_H
#define APP_MOTOR_H

#include <stdint.h>

void app_motor_init(void);
void set_motor_speed(int left_val, int right_val);

#endif
