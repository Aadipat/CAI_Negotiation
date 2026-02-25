AGENT_POOL = ['Random', 'Boulware', 'Tit-For-Tat', 'Group2', 'Group3', 'Group5', 'Group6', 'Group7', 'Group9', 'Group10', 'Group11', 'Groupn', 'AgentX', 'AresParty', 'Atlas3', 'DrageKnight', 'JonnyBlack', 'ParsAgent', 'RandomDance', 'SENGOKU', 'TUDMixedStrategyAgent', 'AgentBuyogMain', 'AgentH', 'CUHKAgent2015', 'kawaii', 'MeanBot', 'PokerFace', 'AgentSmith2016', 'Caduceus', 'ClockworkAgent', 'Farma', 'GrandmaAgent', 'MyAgent', 'Ngent', 'SYAgent', 'Terra', 'AgentF', 'Farma17', 'PonPokoAgent', 'TucAgent']

class Strategy:
    def __init__(self, model, name, feature) -> None:
        self.model = model
        self.name = name
        self.feature = feature

    def __call__(self, state):
        action, _ = self.model.predict(state, deterministic=True)
        return action