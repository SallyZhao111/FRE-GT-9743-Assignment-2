import pandas as pd
from typing import List, Optional, Union
import QuantLib as ql
from fixedincomelib.market.basics import *
from fixedincomelib.market.registries import IndexRegistry, DataConventionRegistry
from fixedincomelib.market.data_conventions import (
    CompoundingMethod,
    # DataConventionRFRFuture,
)
from fixedincomelib.market import (
    Currency,
    AccrualBasis,
    BusinessDayConvention,
    HolidayConvention,
    DataConventionRegistry,
    IndexRegistry,
    # DataConventionRFRFuture,
)
from fixedincomelib.product.utilities import LongOrShort, PayOrReceive
from fixedincomelib.product.product_interfaces import (
    Product,
    ProductVisitor,
    ProductBuilderRegistry,
)
from fixedincomelib.date import (
    Date,
    Period,
    TermOrTerminationDate,
    make_schedule,
    accrued,
)
from fixedincomelib.product.product_portfolio import ProductPortfolio


class ProductBulletCashflow(Product):

    _version = 1
    _product_type = "PRODUCT_BULLET_CASHFLOW"

    def __init__(
        self,
        termination_date: Date,
        currency: Currency,
        notional: float,
        long_or_short: LongOrShort,
        payment_date: Optional[Date] = None,
    ) -> None:

        super().__init__()
        self.first_date_ = self.last_date_ = termination_date
        self.long_or_short_ = long_or_short
        self.notional_ = notional
        self.currency_ = currency
        self.paymnet_date_ = self.last_date_ if payment_date is None else payment_date

    @property
    def termination_date(self) -> Date:
        return self.last_date

    @property
    def payment_date(self) -> Date:
        return self.paymnet_date_


class ProductFixedAccrued(Product):

    _version = 1
    _product_type = "PRODUCT_FIXED_ACCRUED"

    def __init__(
        self,
        effective_date: Date,
        termination_date: Date,
        currency: Currency,
        notional: float,
        accrual_basis: AccrualBasis,
        payment_date: Optional[Date] = None,
        business_day_convention: Optional[
            BusinessDayConvention
        ] = BusinessDayConvention("F"),
        holiday_convention: Optional[HolidayConvention] = HolidayConvention("USGS"),
    ) -> None:

        super().__init__()
        self.effective_date_ = self.first_date_ = effective_date
        self.termination_date_ = self.last_date_ = termination_date
        self.long_or_short_ = LongOrShort.LONG if notional >= 0 else LongOrShort.SHORT
        self.notional_ = notional
        self.currency_ = currency
        self.accrual_basis_ = accrual_basis
        self.business_day_convention_ = business_day_convention
        self.holiday_convention_ = holiday_convention
        self.paymnet_date_ = self.termination_date_
        if payment_date is not None:
            self.paymnet_date_ = payment_date
        # calc accrued
        self.accrued_ = accrued(
            self.effective_date_,
            self.termination_date_,
            self.accrual_basis_,
            self.business_day_convention_,
            self.holiday_convention_,
        )

    @property
    def effective_date(self) -> Date:
        return self.effective_date_

    @property
    def termination_date(self) -> Date:
        return self.termination_date_

    @property
    def accrual_basis(self) -> AccrualBasis:
        return self.accrual_basis_

    @property
    def payment_date(self) -> Date:
        return self.paymnet_date_

    @property
    def business_day_convention(self) -> BusinessDayConvention:
        return self.business_day_convention_

    @property
    def holiday_convention(self) -> HolidayConvention:
        return self.holiday_convention_

    @property
    def accrued(self) -> float:
        return self.accrued_


class ProductOvernightIndexCashflow(Product):

    _version = 1
    _product_type = "PRODUCT_OVERNIGHT_INDEX_CASHFLOW"

    def __init__(
        self,
        effective_date: Date,
        term_or_termination_date: TermOrTerminationDate,
        on_index: str,
        compounding_method: CompoundingMethod,
        spread: float,
        notional: float,
        payment_date: Optional[Date] = None,
    ) -> None:

        super().__init__()

        # get index
        self.on_index_str_ = on_index
        self.on_index_: ql.QuantLib.OvernightIndex = IndexRegistry().get(
            self.on_index_str_
        )
        # sort out date
        self.first_date_ = self.effective_date_ = effective_date
        self.termination_date_ = term_or_termination_date.get_date()
        if term_or_termination_date.is_term():
            calendar: ql.QuantLib.Calendar = self.on_index_.fixingCalendar()
            self.termination_date_ = Date(
                calendar.advance(
                    self.effective_date_,
                    term_or_termination_date.get_term(),
                    self.on_index.businessDayConvention(),
                )
            )  # need to find a way to get biz_day_conv from index
        self.last_date_ = self.termination_date_
        self.paymentDate_ = (
            self.termination_date_ if payment_date is None else payment_date
        )
        # other attributes
        self.notional_ = notional
        self.long_or_short_ = LongOrShort.LONG if notional >= 0 else LongOrShort.SHORT
        self.compounding_method_ = compounding_method
        self.spread_ = spread
        self.currency_ = Currency(self.on_index_.currency().code())

    @property
    def on_index(self) -> ql.QuantLib.OvernightIndex:
        return self.on_index_

    @property
    def compounding_method(self) -> CompoundingMethod:
        return self.compounding_method_

    @property
    def effective_date(self) -> Date:
        return self.effective_date_

    @property
    def termination_date(self) -> Date:
        return self.termination_date_

    @property
    def spread(self) -> float:
        return self.spread_

    @property
    def payment_date(self) -> Date:
        return self.paymentDate_

    def accept(self, visitor: ProductVisitor):
        return visitor.visit(self)

    def serialize(self) -> dict:
        content = {}
        content["VERSION"] = self._version
        content["TYPE"] = self._product_type
        content["EFFECTIVE_DATE"] = self.effective_date.ISO()
        content["TERMINATION_DATE"] = self.termination_date.ISO()
        content["PAYMENT_DATE"] = self.payment_date.ISO()
        content["ON_INDEX"] = self.on_index_str_
        content["SPREAD"] = self.spread
        content["COMPOUNDING_METHOD"] = self.compounding_method.to_string().upper()
        content["NOTIONAL"] = self.notional
        return content

    @classmethod
    def deserialize(cls, input_dict) -> "ProductOvernightIndexCashflow":
        effective_date = Date(input_dict["EFFECTIVE_DATE"])
        termination_date = TermOrTerminationDate(input_dict["TERMINATION_DATE"])
        payment_date = Date(input_dict["PAYMENT_DATE"])
        on_index = input_dict["ON_INDEX"]
        spread = float(input_dict["SPREAD"])
        compounding_method = CompoundingMethod.from_string(
            input_dict["COMPOUNDING_METHOD"]
        )
        notional = float(input_dict["NOTIONAL"])
        return cls(
            effective_date,
            termination_date,
            on_index,
            compounding_method,
            spread,
            notional,
            payment_date,
        )


class ProductRFRFuture(Product):

    _version = 1
    _product_type = "PRODUCT_RFR_FUTURE"

    def __init__(
        self,
        effective_date: Date,
        term_or_termination_date: TermOrTerminationDate,
        future_conv: str,
        long_or_short: LongOrShort,
        amount: float,
        strike: Optional[float] = 0.0,
    ) -> None:

        super().__init__()


### TODO
class InterestRateStream(ProductPortfolio):

    def __init__(
        self,
        effective_date: Date,
        termination_date: Date,
        accrual_period: Period,
        notional: float,
        currency: Currency,
        accrual_basis: AccrualBasis,
        buseinss_day_convention: BusinessDayConvention,
        holiday_convention: HolidayConvention,
        float_index: Optional[str] = None,
        fixed_rate: Optional[float] = None,
        is_on_index: Optional[bool] = True,
        # has default values
        ois_compounding: Optional[CompoundingMethod] = CompoundingMethod.COMPOUND,
        ois_spread: Optional[float] = 0.0,
        fixing_in_arrear: Optional[bool] = True,
        payment_offset: Optional[Period] = Period("0D"),
        payment_business_day_convention: Optional[
            BusinessDayConvention
        ] = BusinessDayConvention("F"),
        payment_holiday_convention: Optional[HolidayConvention] = HolidayConvention(
            "USGS"
        ),
        rule: Optional[str] = "BACKWARD",
        end_of_month: Optional[bool] = False,
    ):

        if float_index is None and fixed_rate is None:
            raise Exception("Cannot have both floating index and fixed rate invalid.")

        ### TODO
        # use utilities functions to make schedule
        sch = make_schedule(
            start_date=effective_date,
            end_date=termination_date,
            accrual_period=accrual_period,
            holiday_convention=holiday_convention,
            business_day_convention=buseinss_day_convention,
            accrual_basis=accrual_basis,
            rule=rule,
            end_of_month=end_of_month,
            fix_in_arrear=fixing_in_arrear,
            fixing_offset=Period("0D"),  
            payment_offset=payment_offset,
            payment_business_day_convention=payment_business_day_convention,
            payment_holiday_convention=payment_holiday_convention,
        )

        

        products, weights = [], []
        

        ### TODO
        for _, row in sch.iterrows():
            s: Date = row["StartDate"]
            e: Date = row["EndDate"]
            p: Date = row["PaymentDate"]

            # Floating component (Overnight Index Cashflow)
            if float_index is not None:
                ois_cf = ProductOvernightIndexCashflow(
                    effective_date=s,
                    term_or_termination_date=TermOrTerminationDate(e.ISO()),
                    on_index=float_index,
                    compounding_method=ois_compounding,
                    spread=ois_spread,
                    notional=notional,
                    payment_date=p,
                )
                products.append(ois_cf)
                weights.append(1.0)

            # Fixed accrued component
            if fixed_rate is not None:
                fixed_cf = ProductFixedAccrued(
                    effective_date=s,
                    termination_date=e,
                    currency=currency,
                    notional=notional * fixed_rate,  # key idea: rate absorbed here
                    accrual_basis=accrual_basis,
                    payment_date=p,
                    business_day_convention=buseinss_day_convention,
                    holiday_convention=holiday_convention,
                )
                products.append(fixed_cf)
                weights.append(1.0)

        super().__init__(products, weights)

    def cashflow(self, i: int) -> Product:
        return self.element(i)

    def num_cashflows(self) -> int:
        return self.num_elements_


### TODO
class ProductRFRSwap(Product):

    _version = 1
    _product_type = "PRODUCT_RFR_SWAP"

    def __init__(
        self,
        effective_date: Date,
        term_or_termination_date: TermOrTerminationDate,
        payment_off_set: Period,
        on_index: str,
        fixed_rate: float,
        pay_or_rec: PayOrReceive,
        notional: float,
        accrual_period: Period,
        accrual_basis: AccrualBasis,
        floating_leg_accrual_period: Optional[Period] = None,
        pay_business_day_convention: Optional[
            BusinessDayConvention
        ] = BusinessDayConvention("F"),
        pay_holiday_convention: Optional[HolidayConvention] = HolidayConvention("USGS"),
        spread: Optional[float] = 0.0,
        compounding_method: Optional[CompoundingMethod] = CompoundingMethod.COMPOUND,
    ) -> None:

        super().__init__()

        self.on_index_str_ = on_index
        self.on_index_: ql.QuantLib.OvernightIndex = IndexRegistry().get(
            self.on_index_str_
        )
        self.pay_business_day_convention_ = pay_business_day_convention
        self.pay_holiday_convention_ = pay_holiday_convention
        self.first_date_ = self.effective_date_ = effective_date
        self.term_or_termination_date_ = term_or_termination_date
        self.termination_date_ = self.term_or_termination_date_.get_date()
        if self.term_or_termination_date_.is_term():
            calendar = self.on_index_.fixingCalendar()
            self.termination_date_ = Date(
                calendar.advance(
                    self.effective_date_,
                    self.term_or_termination_date_.get_term(),
                    self.on_index_.businessDayConvention(),
                )
            )
        self.last_date_ = self.termination_date_
        # other attributes
        self.currency_ = Currency(self.on_index_.currency().code())
        self.fixed_rate_ = fixed_rate
        self.notional_ = notional
        self.spread_ = spread
        self.pay_or_rec_ = pay_or_rec
        self.long_or_short_ = LongOrShort.LONG if notional > 0 else LongOrShort.SHORT
        self.pay_offset_ = payment_off_set
        self.accrual_basis_ = accrual_basis
        self.accrual_period_ = accrual_period
        self.floating_leg_accrual_period_ = (
            self.accrual_period_
            if floating_leg_accrual_period is None
            else floating_leg_accrual_period
        )
        self.compounding_method_ = compounding_method
        fixed_leg_sign = 1.0 if self.pay_or_rec_ == PayOrReceive.PAY else -1.0
       
        floating_leg_notional = -fixed_leg_sign * self.notional_
        fixed_leg_notional = fixed_leg_sign * self.notional_

        # floating leg
        ### TODO
        
        self.floating_leg_ = InterestRateStream(
            effective_date=self.effective_date_,
            termination_date=self.termination_date_,
            accrual_period=self.floating_leg_accrual_period_,
            notional=floating_leg_notional,
            currency=self.currency_,
            accrual_basis=self.accrual_basis_,
            buseinss_day_convention=self.pay_business_day_convention_,
            holiday_convention=self.pay_holiday_convention_,
            float_index=self.on_index_str_,
            fixed_rate=None,
            is_on_index=True,
            ois_compounding=self.compounding_method_,
            ois_spread=self.spread_,
            fixing_in_arrear=True,
            payment_offset=self.pay_offset_,
            payment_business_day_convention=self.pay_business_day_convention_,
            payment_holiday_convention=self.pay_holiday_convention_,
            rule="BACKWARD",
            end_of_month=False,
        )
        # fixed leg
        ### TODO
        # fixed leg
        self.fixed_leg_ = InterestRateStream(
            effective_date=self.effective_date_,
            termination_date=self.termination_date_,
            accrual_period=self.accrual_period_,
            notional=fixed_leg_notional,
            currency=self.currency_,
            accrual_basis=self.accrual_basis_,
            buseinss_day_convention=self.pay_business_day_convention_,
            holiday_convention=self.pay_holiday_convention_,
            float_index=None,
            fixed_rate=self.fixed_rate_,
            is_on_index=False,
            payment_offset=self.pay_offset_,
            payment_business_day_convention=self.pay_business_day_convention_,
            payment_holiday_convention=self.pay_holiday_convention_,
            rule="BACKWARD",
            end_of_month=False,
        )

    def floating_leg_cash_flow(self, i: int) -> Product:
        assert 0 <= i < self.floating_leg_.num_cashflows()
        return self.floating_leg_.element(i)

    def fixed_leg_cash_flow(self, i: int) -> Product:
        assert 0 <= i < self.fixed_leg_.num_cashflows()
        return self.fixed_leg_.element(i)

    @property
    def effective_date(self) -> Date:
        return self.effective_date_

    @property
    def termination_date(self) -> Date:
        return self.termination_date_

    @property
    def term_or_termination_date(self) -> Date:
        return self.term_or_termination_date_

    @property
    def pay_offset(self) -> Period:
        return self.pay_offset_

    @property
    def fixed_rate(self) -> float:
        return self.fixed_rate_

    @property
    def spread(self) -> float:
        return self.spread_

    @property
    def on_index(self) -> ql.QuantLib.OvernightIndex:
        return self.on_index_

    @property
    def pay_or_rec(self) -> PayOrReceive:
        return self.pay_or_rec_

    @property
    def compounding_method(self) -> CompoundingMethod:
        return self.compounding_method_

    @property
    def accrual_period(self) -> Period:
        return self.accrual_period_

    @property
    def floating_leg_accrual_period(self) -> Period:
        return self.floating_leg_accrual_period_

    @property
    def accrual_basis(self) -> AccrualBasis:
        return self.accrual_basis_

    @property
    def pay_business_day_convention(self) -> BusinessDayConvention:
        return self.pay_business_day_convention_

    @property
    def pay_holiday_convention(self) -> HolidayConvention:
        return self.pay_holiday_convention_
