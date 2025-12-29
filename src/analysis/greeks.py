import numpy as np
from scipy.stats import norm
from typing import Dict, Any, Optional
import math

class GreeksCalculator:
    """
    Calculate Option Greeks using Black-Scholes-Merton model.
    """
    
    @staticmethod
    def calculate_d1_d2(S: float, K: float, T: float, r: float, sigma: float):
        """
        S: Underlying Price
        K: Strike Price
        T: Time to Expiration (in years)
        r: Risk-free Interest Rate
        sigma: Implied Volatility
        """
        if T <= 0 or sigma <= 0:
            return None, None
            
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        return d1, d2

    @staticmethod
    def calculate_call_greeks(S: float, K: float, T: float, r: float, sigma: float) -> Dict[str, float]:
        """
        Calculate Delta, Gamma, Theta, Vega, Rho for a Call Option.
        """
        if T <= 0:
            return {
                "delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0, "theoretical_price": 0.0
            }

        # Sanity checks
        if sigma <= 0 or S <= 0 or K <= 0:
             return {
                "delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0, "theoretical_price": 0.0
            }

        try:
            d1, d2 = GreeksCalculator.calculate_d1_d2(S, K, T, r, sigma)
            if d1 is None:
                return {}

            # Cumulative and PDF
            N_d1 = norm.cdf(d1)
            N_d2 = norm.cdf(d2)
            pdf_d1 = norm.pdf(d1)

            # Price
            price = S * N_d1 - K * np.exp(-r * T) * N_d2

            # Greeks
            delta = N_d1
            gamma = pdf_d1 / (S * sigma * np.sqrt(T))
            
            # Theta (daily) - usually calculated as annual / 365
            theta_annual = -(S * pdf_d1 * sigma) / (2 * np.sqrt(T)) - r * K * np.exp(-r * T) * N_d2
            theta = theta_annual / 365.0
            
            # Vega (for 1% change in volatility)
            vega = S * np.sqrt(T) * pdf_d1 * 0.01
            
            rho = K * T * np.exp(-r * T) * N_d2 * 0.01

            return {
                "delta": float(delta),
                "gamma": float(gamma),
                "theta": float(theta),
                "vega": float(vega),
                "rho": float(rho),
                "theoretical_price": float(price)
            }
        except Exception:
            return {}
