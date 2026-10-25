/** Foreign-currency selection, converted amount and exchange-rate controls. */

import { useTranslation } from 'react-i18next'

import { Button } from '../ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/Card'
import { FormField } from '../ui/Form'
import { Input } from '../ui/Input'
import { Select } from '../ui/Select'

/**
 * @param {{
 *   selectedCurrency: string,
 *   setSelectedCurrency: (value: string) => void,
 *   currencyOptions: {value: string, label: string}[],
 *   foreign: boolean,
 *   repayment: boolean,
 *   originalAmountInput: string,
 *   updateOriginalAmount: (value: string) => void,
 *   conversionRateInput: string,
 *   setConversionRateInput: (value: string) => void,
 *   useCustomRate: boolean,
 *   toggleCustomRate: () => void,
 *   refreshRate: () => void,
 *   rateState: {status: string, rate: number|null, message: string},
 *   rate: number|null,
 *   group: any,
 * }} props
 */
export function ExpenseCurrencyCard({
  selectedCurrency,
  setSelectedCurrency,
  currencyOptions,
  foreign,
  repayment,
  originalAmountInput,
  updateOriginalAmount,
  conversionRateInput,
  setConversionRateInput,
  useCustomRate,
  toggleCustomRate,
  refreshRate,
  rateState,
  rate,
  group,
}) {
  const { t } = useTranslation()

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('ExpenseForm.Expense.currencyField.label', 'Currency of expense')}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <FormField
          label={t('ExpenseForm.Expense.currencyField.label', 'Currency of expense')}
          htmlFor="expense-currency"
        >
          <Select
            id="expense-currency"
            value={selectedCurrency}
            options={currencyOptions}
            onChange={setSelectedCurrency}
          />
        </FormField>

        {foreign ? (
          <>
            <FormField
              label={
                repayment
                  ? t('ExpenseForm.originalAmountField.repaymentLabel', 'Amount to transfer')
                  : t('ExpenseForm.originalAmountField.label', 'Amount to convert')
              }
              htmlFor="expense-original-amount"
            >
              <Input
                id="expense-original-amount"
                name="originalAmount"
                inputMode="decimal"
                value={originalAmountInput}
                readOnly={repayment}
                onChange={(event) => updateOriginalAmount(event.target.value)}
              />
            </FormField>
            <div className="sm:col-span-2 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              {rateState.status === 'loading' ? (
                <span>{t('ExpenseForm.conversionRateState.loading', 'Getting exchange rates…')}</span>
              ) : rate ? (
                <span>
                  {selectedCurrency} 1 = {group.currency_code} {Number(rate).toFixed(2)}
                </span>
              ) : (
                <span>
                  {rateState.message ||
                    t('ExpenseForm.conversionRateState.noRate', 'Enter a custom rate below.')}
                </span>
              )}
              <Button variant="ghost" size="sm" onClick={toggleCustomRate}>
                {useCustomRate
                  ? t('ExpenseForm.conversionRateField.useApi', 'Use rates from Frankfurter')
                  : t('ExpenseForm.conversionRateField.useCustom', 'Use custom rate')}
              </Button>
              <Button variant="outline" size="sm" onClick={refreshRate}>
                {t('ExpenseForm.conversionRateState.refresh', 'Refresh')}
              </Button>
            </div>
            {useCustomRate ? (
              <FormField
                label={t('ExpenseForm.conversionRateField.label', 'Exchange rate')}
                htmlFor="expense-rate"
              >
                <Input
                  id="expense-rate"
                  name="conversionRate"
                  inputMode="decimal"
                  value={conversionRateInput}
                  onChange={(event) => setConversionRateInput(event.target.value)}
                />
              </FormField>
            ) : null}
          </>
        ) : null}
      </CardContent>
    </Card>
  )
}
