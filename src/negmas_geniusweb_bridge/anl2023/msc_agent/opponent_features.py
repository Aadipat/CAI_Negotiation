import numpy as np

def get_opponent_features(negotiator, final_offer=None):
    # Calculate Concesssion rate
    u_min =  min(negotiator.partner_utils)
    # fyu = float(negotiator.opponent_model.get_predicted_utility(negotiator._best))
    fyu = float(negotiator.opponent_model(negotiator._best))
    consession_rate = (1 - u_min) / (1 - fyu) if u_min > fyu else 1

    # Calculate Average rate
    u_avg = np.mean(negotiator.partner_utils)
    average_rate = (1 -  u_avg) / (1 - fyu) if u_avg > fyu else 1

    # Calculate Default configuration performance
    u_agree = float(negotiator.profile.getUtility(final_offer)) if final_offer is not None else 0
    u_lower = float(negotiator.profile.getUtility(negotiator.partner_offers[np.argmax(negotiator.partner_utils)]))
    dcp = (u_agree - u_lower) / (1 - u_lower) if u_agree > u_lower else 0

    return np.array([consession_rate, average_rate, dcp])