import logging
from random import randint
from typing import cast
from decimal import Decimal
from time import time as clock
import datetime
from json import dump, load
import math
from os.path import exists

from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.LearningDone import LearningDone
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.issuevalue.Value import Value
from geniusweb.issuevalue.ValueSet import ValueSet
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profileconnection.ProfileConnectionFactory import ProfileConnectionFactory
from geniusweb.progress.ProgressRounds import ProgressRounds
from geniusweb.progress.ProgressTime import ProgressTime
from geniusweb.issuevalue.DiscreteValue import DiscreteValue

from geniusweb.profileconnection.ProfileInterface import ProfileInterface
from geniusweb.profile.utilityspace.LinearAdditive import LinearAdditive

from .utils.Pair import Pair



class SmartAgent(DefaultParty):
    """
    Offers random bids until a bid with sufficient utility is offered.
    """
    def __init__(self):
        super().__init__()
        self.getReporter().log(logging.INFO,"party is initialized")
        self._profile: ProfileInterface = None
        self._lastReceivedBid:Bid = None
        self._lastreceivedutil = 0
        self.profile: LinearAdditive = None
        self._progress: ProgressTime = None
        self.domain: Domain = None
        self._utilspace: LinearAdditive = None
        self.parameter = None

        self.filepath: str = None
        self.summary: dict = None
        self.round_times: list[Decimal] = []
        self.me: PartyId = None
        self.other: str = None
        self.received_bids: list = []#接收到的出价
        self.received_utils: list = []#接收到的出价的效用
        self.proposed_bid: list = []#提出的出价
        self.light_proposed: list = []#妥协阶段提出的出价
        self._sorted_bids: list = []#出价按效用从上至下排序
        self._bestreceivedutil = 0#最佳接收效用
        self._bestreceivedbid : Bid= None#最佳接收出价
        self.last_time = None
        self.avg_time = None
        self.threshold = 0.99#最后一回合
        self.light_threshold = 0.95#试探阶段的结束,之后进入妥协阶段
        self.last_propose:Bid = None#最后出价
        self.top = 0#最后一个优秀Bid
        self.freqMap: dict = None#频率表
        self.tSplit = 40#中后期时间段分段
        self.ind = 0#时间段指针
        self.opCounter: list = [0] * self.tSplit#对手在不同时间段的出价次数
        self.opSum: list = [0.0] * self.tSplit#对手在不同时间段的收益总和
        self.uniq:list = [0] * self.tSplit#对手在不同时间段的新offer
        self.av:list = [0.0] * self.tSplit#对手在不同时间段的对手收益平均值
        self.uniqreceive:list = []#对手在不同时间段的接受出价
        self.front:list = [0]#前期接收Bid
        self.th = 0
        self.bao = 1#认为有保险
        self.have_load = 0#数据加载标记
        self.is_hard = 0 #认为对手是hard型
        self.is_micro = 0#认为对手是micro


    # Override
    def notifyChange(self, info: Inform):
        #self.getReporter().log(logging.INFO,"received info:"+str(info))
        if isinstance(info,Settings) :
            self._settings:Settings=cast(Settings,info)
            self.me = self._settings.getID()
            self.parameter = self._settings.getParameters()
            self.storage_dir = self.parameter.get("storage_dir")
            #self.storage_dir = "."
            self._me = self._settings.getID()
            self._protocol:str = str(self._settings.getProtocol().getURI())
            self._progress = self._settings.getProgress()
            if "Learn" ==  self._protocol:
                self.getConnection().send(LearningDone(self._me)) #type:ignore
            else:
                self._profile = ProfileConnectionFactory.create(info.getProfile().getURI(), self.getReporter())
            self.profile = self._profile.getProfile()
            self.domain = self.profile.getDomain()
            self.progress = self._settings.getProgress()
            if self.freqMap == None:
                # Map wasn't created before, create a new instance now
                self.freqMap = {}
            else:
                # Map was created before, but this is a new negotiation scenario, clear the old map.
                self.freqMap.clear()
            issues: set = self.domain.getIssues()
            for s in issues:
                # create new list of all the values for
                p: Pair = Pair()
                p.vList = {}

                # gather type of issue based on the first element
                vs: ValueSet = self.domain.getValues(s)
                if isinstance(vs.get(0), DiscreteValue):
                    p.type = 0
                elif isinstance(vs.get(0), NumberValue):
                    p.type = 1

                # Obtain all of the values for an issue "s"
                for v in vs:
                    # Add a new entry in the frequency map for each(s, v, typeof(v))
                    vStr: str = self.valueToStr(v, p)
                    p.vList[vStr] = 0

                self.freqMap[s] = p

            all_bids = AllBidsList(self.domain)
            _bid_to_utility = {bid: self.profile.getUtility(bid) for bid in all_bids}
            self._sorted_bids = sorted(_bid_to_utility, key=lambda bid: _bid_to_utility[bid], reverse=True)
            for i in range(len(self._sorted_bids)):
                if self.profile.getUtility(self._sorted_bids[i]) >= 0.9:
                    self.top += 1
                else:
                    break


        elif isinstance(info, ActionDone):
            action:Action=cast( ActionDone,info).getAction()
            actor = action.getActor()
            if actor != self.me:
                self.other = str(actor).rsplit("_", 1)[0]
                type:str = "learn"
                filename = self.other + type
                self.filepath = f"{self.storage_dir}/{filename}.json"
                if self.have_load == 0 and exists(self.filepath):
                    self.load_data()
                    self.have_load = 1
            if isinstance(action, Offer):
                #提取对手出价及其效用
                self._lastReceivedBid = cast(Offer, action).getBid()
                self._lastreceivedutil = self.profile.getUtility(self._lastReceivedBid)
                #对手模型建立和更新
                '''if self.opponent_model is None:
                    self.opponent_model = OpponentModel(self.domain)'''
                #time = self.progress.get(clock() * 1000)
                #self.opponent_model.update(self._lastReceivedBid, time)
                self.updateFreqMap(self._lastReceivedBid)


        elif isinstance(info, YourTurn):
            self._myTurn()
            if isinstance(self._progress, ProgressRounds) :
                self._progress = self._progress.advance()
        elif isinstance(info, Finished):
            # 当在试探保险机制后对手拒绝则是为无保险机制
            agreement = info.getAgreements()
            print(agreement)
            print("{} {}".format("last propose as utility:",self.profile.getUtility(self.last_propose)))
            self.save_data(agreement)
            self.terminate()
        else:
            self.getReporter().log(logging.WARNING, "Ignoring unknown info "+str(info))


    # Override
    def getCapabilities(self) -> Capabilities:
        return Capabilities( set([ "SAOP", "Learn", "MOPAC"]), set(['geniusweb.profile.utilityspace.LinearAdditive']))

    # Override
    def getDescription(self) -> str:
        return "An agent for college graduation, which is needed to beat other agents competed in ANL2022"

    # Override
    def terminate(self):
        self.getReporter().log(logging.INFO,"party is terminating:")
        super().terminate()
        if self._profile != None:
            self._profile.close()
            self._profile = None


    def _myTurn(self):
        #print(self.target)
        #此步骤是在计算一回合需要的平均时间
        if self.last_time is not None:
            self.round_times.append(datetime.datetime.now().timestamp() - self.last_time.timestamp())
            self.avg_time = sum(self.round_times[-5:])/5
        self.last_time = datetime.datetime.now()

        time = self.progress.get(clock() * 1000)

        #计算每个时间段的平均对手收益
        if time > 0.2:
            index: int = (int)((self.tSplit - 1) * ((time - 0.2) / (1 - 0.2)))
            if self._lastReceivedBid != None:
                self.opSum[index] += self.calcOpValue(self._lastReceivedBid)
                self.opCounter[index] += 1
                if self._lastReceivedBid not in self.uniqreceive:
                    self.uniqreceive.append(self._lastReceivedBid)
                    self.uniq[index] += 1
            if index > self.ind:
                #print(self.opSum[self.ind]/self.opCounter[self.ind])
                self.uniqreceive = []
                self.ind += 1
                self.uniq[self.ind-1] = min(self.uniq[self.ind-1],self.th)


        #更新新offer数,接收Bid,前期接收Bid
        if self._lastReceivedBid is not None:
            if self._lastReceivedBid not in self.received_bids:
                self.th += 1
            #print(self.calcOpValue(self._lastReceivedBid))
            if self._lastreceivedutil > self._bestreceivedutil:
                self._bestreceivedbid = self._lastReceivedBid
                self._bestreceivedutil = self._lastreceivedutil
            self.received_bids.append(self._lastReceivedBid)
            self.received_utils.append(self._bestreceivedutil)
            if time <= 0.2:
                self.front.append(self._lastReceivedBid)


        #更新最后几个回合的时间
        if self.avg_time is not None:

            self.threshold = 1 - 1000 * self.avg_time / self.progress.getDuration()
            self.light_threshold = 1 - 7000 * self.avg_time / self.progress.getDuration()

        mybid = self.getBid()

        #在认为有保险且最后回合重复前期出价则视为hard型代理
        if time > self.light_threshold :
            if self.bao == 1 and self._lastReceivedBid in self.front:
                #print("{}".format("这大概是hard型吧?"))
                self.is_hard = 1
                mybid = self._sorted_bids[0]
            else:
                mybid = self._bestreceivedbid

        # 对micro的专属对策
        if self.is_micro == 1:
            mybid = self._sorted_bids[self.th]

        #投降机制
        if mybid == None :
            mybid = self._sorted_bids[0]

        #主体采用ACnext的接受条件,针对非Hard型代理
        if self.is_good(self._lastReceivedBid,mybid):
            print("{} {}".format("agent accept as utility:",self._lastreceivedutil))
            action = Accept(self._me, self._lastReceivedBid)
        else:
            self.last_propose = mybid
            self.proposed_bid.append(mybid)
            #print(self.profile.getUtility(self.last_propose))
            action = Offer(self._me, mybid);
        self.getConnection().send(action)

    def is_good(self,lastReceivedBid,mybid):
        if lastReceivedBid is None:
            return False

        time = self.progress.get(clock() * 1000)
        thrshould = 0.9
        '''if self.opCounter[max(0,self.ind-1)] != 0:
            thrshould = self.opSum[max(0,self.ind-1)]/self.opCounter[max(0,self.ind-1)]'''
        thrshould = self.profile.getUtility(self._sorted_bids[self.th])

        condition = [
            self._lastreceivedutil >= thrshould and self.is_hard != 1 and self.bao == 1,
            self._lastreceivedutil >= self.profile.getUtility(mybid),
            (time >= self.threshold and self.is_hard != 1 and self.bao == 1),
            self.is_micro == 1 and self._lastreceivedutil >= self.profile.getUtility(self._sorted_bids[self.th])
        ]
        return (any(condition) and self.profile.getUtility(self._lastReceivedBid) >= 0.6)

    def getBid(self):
        if self.last_propose is None:
            return self._sorted_bids[0]

        bid = None

        time = self.progress.get(clock() * 1000)
        thrshould = 0.9
        if self.opCounter[max(0,self.ind-1)] != 0:
            thrshould = max(self.opSum[max(0,self.ind-1)] / self.opCounter[max(0,self.ind-1)],0.7)


        if time <= 0.21 :
            bid = self._sorted_bids[randint(0,min(self.top,round(1/100 * len(self._sorted_bids))))]
        else:
            for i in range(len(self._sorted_bids)):
                if self.profile.getUtility(self._sorted_bids[i]) < thrshould \
                        and self.profile.getUtility(self._sorted_bids[i]) >= 0.6:
                    #print(i+self.uniq[self.ind])
                    bid = self._sorted_bids[randint(0,max(0,i+self.uniq[self.ind-1])-1)]
                    break

        if bid == None:
            bid = self._sorted_bids[0]

        return bid

    #对手模型预测,更新
    def calcOpValue(self, bid: Bid):
        value: float = 0

        issues = bid.getIssues()
        valUtil: list = [0] * len(issues)
        issWeght: list = [0] * len(issues)
        k: int = 0  # index

        for s in issues:
            p: Pair = self.freqMap[s]
            v: Value = bid.getValue(s)
            vs: str = self.valueToStr(v, p)

            # calculate utility of value (in the issue)
            sumOfValues: int = 0
            maxValue: int = 1
            for vString in p.vList.keys():
                sumOfValues += p.vList[vString]
                maxValue = max(maxValue, p.vList[vString])

            # calculate estimated utility of the issuevalue
            valUtil[k] = p.vList.get(vs) / maxValue

            # calculate the inverse std deviation of the array
            mean: float = sumOfValues / len(p.vList)
            for vString in p.vList.keys():
                issWeght[k] += pow(p.vList.get(vString) - mean, 2)
            issWeght[k] = 1.0 / math.sqrt((issWeght[k] + 0.1) / len(p.vList))

            k += 1

        sumOfWght: float = 0
        for k in range(len(issues)):
            value += valUtil[k] * issWeght[k]
            sumOfWght += issWeght[k]

        return value / sumOfWght

    def updateFreqMap(self, bid: Bid):
        if not (bid == None):
            issues = bid.getIssues()

            for s in issues:
                p: Pair = self.freqMap.get(s)
                v: Value = bid.getValue(s)

                vs: str = self.valueToStr(v, p)
                p.vList[vs] = (p.vList.get(vs) + 1)

    def valueToStr(self, v: Value, p: Pair):
        v_str: str = ""
        if p.type == 0:
            v_str = cast(DiscreteValue, v).getValue()
        elif p.type == 1:
            v_str = cast(NumberValue, v).getValue()

        if v_str == "":
            print("Warning: Value wasn't found")
        return v_str

    #数据储存,加载
    def save_data(self,agreements):
        if len(set(self.proposed_bid)) == len(set(self.received_bids)):
            self.is_micro = 1
        if agreements.getMap() == None or agreements.getMap() == {}:
            self.bao = 0
        for i in range(self.tSplit):
            if self.opCounter[i] == 0:
                self.av[i] = 0
            else:
                self.av[i] = self.opSum[i]/self.opCounter[i]
        with open(self.filepath, "w") as f:
            dump({
                "bao": self.bao,
                "av": self.av,
                "is_micro": self.is_micro
            }, f)

    def load_data(self):
        if self.filepath is not None:
            with open(self.filepath, "r") as f:
                self.summary = load(f)
            self.bao = self.summary["bao"]
            self.av = self.summary["av"]
            self.is_micro = self.summary["is_micro"]
            for i in range(self.tSplit):
                if self.av[i] != 0:
                    self.opSum[i] += self.av[i]
                    self.opCounter[i] += 1