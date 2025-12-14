import math

class InverseKinematics:
    def __init__(self, l1, l2):
        self.l1 = float(l1)
        self.l2 = float(l2)
        # Pre-allocate result tuple to avoid some allocations if possible 
        # (Though returning simple floats is usually fine in basic micropython)
        
    def solve(self, x, y, z):
        """
        Solves IK for (x, y, z) coordinates.
        Returns (base_deg, shoulder_deg, elbow_deg) or None if unreachable.
        """
        # 1. Base Angle (Simple trigonometry)
        # Note: At x=0, atan2 handles it correctly (90 or -90 deg implied by y sign)
        base_angle_rad = math.atan2(y, x)
        base_angle = math.degrees(base_angle_rad)
        
        # 2. Planar Projection (Reach r)
        # Distance from base center to target on ground plane
        r = math.sqrt(x*x + y*y)
        
        # 3. Geometric Triangle Solution for 2-Link Arm
        # We assume the shoulder joint is at height 0 relative to logical Origin used here
        # If there is a base offset (height), z must be adjusted before calling this.
        
        # Distance 'c' from shoulder pivot to target
        # c^2 = r^2 + z^2
        c_sq = r*r + z*z
        c = math.sqrt(c_sq)
        
        # Check Reachability
        if c > (self.l1 + self.l2):
            return None # Out of reach
            
        # Law of Cosines
        # a^2 = b^2 + c^2 - 2bc cos(A)
        # We need angles inside the triangle formed by L1, L2, C
        
        # Angle opposite to L2 (alpha_1 part of shoulder)
        # L2^2 = L1^2 + c^2 - 2*L1*c * cos(alpha_1)
        # cos(alpha_1) = (L1^2 + c^2 - L2^2) / (2*L1*c)
        
        try:
            cos_a1 = (self.l1**2 + c_sq - self.l2**2) / (2 * self.l1 * c)
            # Clamp for floating point errors near limits
            if cos_a1 > 1.0: cos_a1 = 1.0
            if cos_a1 < -1.0: cos_a1 = -1.0
            alpha_1 = math.acos(cos_a1)
            
            # Angle of elevation of the target vector C
            alpha_2 = math.atan2(z, r)
            
            # Shoulder Angle (Physics: Usually relative to horizon)
            shoulder_angle_rad = alpha_1 + alpha_2
            shoulder_angle = math.degrees(shoulder_angle_rad)
            
            # Elbow Angle
            # Angle opposite to C (Gamma inside) -> External angle for servo?
            # c^2 = L1^2 + L2^2 - 2*L1*L2*cos(gamma_internal)
            
            cos_gamma = (self.l1**2 + self.l2**2 - c_sq) / (2 * self.l1 * self.l2)
            if cos_gamma > 1.0: cos_gamma = 1.0
            if cos_gamma < -1.0: cos_gamma = -1.0
            gamma = math.acos(cos_gamma)
            
            # For this arm, usually 0 is straight? or 90 is straight?
            # Standard: if Link1 and Link2 are straight, angle is 0.
            # But inside triangle, angle is 180.
            # Let's return the internal elbow angle or relative?
            # Usually: Elbow = 180 - internal_angle
            elbow_angle_rad = math.pi - gamma 
            # OR just return the internal angle if the servo calibration handles the mapping.
            # Let's return the geometric angle relative to L1:
            # - If fully folded back: 180?
            # - If straight: 0?
            # Let's stick to standard internal angle logic:
            elbow_angle = math.degrees(gamma) 
            
            # Note on MK2 Logic:
            # The MK2 has a parallel linkage for the upper arm.
            # This often simplifies/complicates things depending on where the servo is.
            # However, user asked for "Kinematics Layer" delivering "Theoretical q".
            # Mapping q -> PWM (Calibration) handles the mechanical linkage offsets.
            # So returning theoretical Shoulder/Elbow angles is correct.
            
            return (base_angle, shoulder_angle, elbow_angle)
            
        except ValueError:
            return None        
