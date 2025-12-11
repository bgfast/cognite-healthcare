#!/usr/bin/env python3
"""
Analyze 2025 YTD claims and calculate estimated costs for each Cigna plan option.
"""

import csv
import re
from decimal import Decimal
from collections import defaultdict

def parse_currency(value):
    """Parse currency values from CSV, handling various formats."""
    if not value or value == 'Not Applicable':
        return Decimal('0.00')
    # Remove commas and dollar signs
    value = str(value).replace('$', '').replace(',', '').strip()
    try:
        return Decimal(value)
    except:
        return Decimal('0.00')

def categorize_claim(row):
    """Categorize a claim based on provider name and type."""
    claim_type = row.get('Type of Claim', '').strip()
    provider = row.get('Provider Name', '').strip().upper()
    
    # Pharmacy claims
    if claim_type == 'PHARMACY':
        return 'pharmacy'
    
    # ER visits
    if any(keyword in provider for keyword in ['ER ', 'EMERGENCY', 'SOUTHEASTERN EMERGENCY']):
        return 'er'
    
    # Urgent care (non-ER urgent care)
    if 'URGENT' in provider:
        return 'urgent_care'
    
    # Preventive care (routine physicals)
    if any(keyword in provider for keyword in ['PHYSICAL', 'PREVENTIVE']):
        return 'preventive'
    
    # Specialist visits (based on common specialist names/patterns)
    # This is a simplification - in reality, you'd need provider specialty data
    # For now, we'll use visit costs and patterns to estimate
    return 'other_medical'

def calculate_plan_costs(claims_data, plan_name, plan_details):
    """Calculate total costs for a given plan based on claims."""
    
    annual_premium = plan_details['monthly_premium'] * 12
    family_deductible = plan_details['family_deductible']
    individual_deductible = plan_details['individual_deductible']
    family_oop_max = plan_details['family_oop_max']
    
    # Track deductible usage per person
    deductible_used = defaultdict(Decimal)
    total_oop = Decimal('0.00')
    
    # Track costs by category
    costs_by_category = defaultdict(Decimal)
    
    for row in claims_data:
        member = row.get('Member Name', '').strip()
        claim_total = parse_currency(row.get('Claim Total', '0'))
        your_responsibility = parse_currency(row.get('Your Responsibility', '0'))
        category = categorize_claim(row)
        
        # For HDHP plan, prescriptions count toward deductible
        # For OAP plans, prescriptions have copays (deductible waived)
        
        if category == 'pharmacy':
            if plan_name == 'HDHP 3400':
                # Prescriptions count toward deductible, then copay
                # We'll estimate tier based on cost
                if claim_total <= 15:
                    tier = 1  # $10 copay after deductible
                elif claim_total <= 50:
                    tier = 2  # $40 copay after deductible
                elif claim_total <= 100:
                    tier = 3  # $50 copay after deductible
                else:
                    tier = 4  # 30% after deductible
                
                # Apply deductible first, then copay
                remaining_deductible = family_deductible - deductible_used[member]
                if remaining_deductible > 0:
                    applied_to_deductible = min(claim_total, remaining_deductible)
                    deductible_used[member] += applied_to_deductible
                    remaining_after_deductible = claim_total - applied_to_deductible
                    
                    if tier == 4:
                        cost = applied_to_deductible + (remaining_after_deductible * Decimal('0.30'))
                    else:
                        copay_amount = [10, 40, 50, 0][tier - 1]
                        cost = applied_to_deductible + Decimal(str(copay_amount))
                else:
                    if tier == 4:
                        cost = claim_total * Decimal('0.30')
                    else:
                        copay_amount = [10, 40, 50, 0][tier - 1]
                        cost = Decimal(str(copay_amount))
            else:
                # OAP plans: copay only (deductible waived for prescriptions)
                if claim_total <= 15:
                    cost = Decimal('10.00')
                elif claim_total <= 50:
                    cost = Decimal('40.00')
                elif claim_total <= 100:
                    cost = Decimal('50.00')
                else:
                    cost = claim_total * Decimal('0.30')
        
        elif category == 'er':
            if plan_name == 'HDHP 3400':
                # 0% after deductible
                remaining_deductible = family_deductible - deductible_used[member]
                if remaining_deductible > 0:
                    applied_to_deductible = min(claim_total, remaining_deductible)
                    deductible_used[member] += applied_to_deductible
                    cost = applied_to_deductible
                else:
                    cost = Decimal('0.00')  # 0% coinsurance
            elif plan_name == 'OAP 750':
                # $150 copay + 20% after deductible
                remaining_deductible = family_deductible - deductible_used[member]
                er_copay = Decimal('150.00')
                if remaining_deductible > 0:
                    applied_to_deductible = min(claim_total - er_copay, remaining_deductible)
                    deductible_used[member] += applied_to_deductible
                    remaining_after_deductible = max(Decimal('0'), claim_total - er_copay - applied_to_deductible)
                    cost = er_copay + applied_to_deductible + (remaining_after_deductible * Decimal('0.20'))
                else:
                    remaining_after_deductible = max(Decimal('0'), claim_total - er_copay)
                    cost = er_copay + (remaining_after_deductible * Decimal('0.20'))
            else:  # OAP 250
                # $150 copay + 10% after deductible
                remaining_deductible = family_deductible - deductible_used[member]
                er_copay = Decimal('150.00')
                if remaining_deductible > 0:
                    applied_to_deductible = min(claim_total - er_copay, remaining_deductible)
                    deductible_used[member] += applied_to_deductible
                    remaining_after_deductible = max(Decimal('0'), claim_total - er_copay - applied_to_deductible)
                    cost = er_copay + applied_to_deductible + (remaining_after_deductible * Decimal('0.10'))
                else:
                    remaining_after_deductible = max(Decimal('0'), claim_total - er_copay)
                    cost = er_copay + (remaining_after_deductible * Decimal('0.10'))
        
        elif category == 'preventive':
            # Preventive care is typically $0 copay, deductible waived
            cost = Decimal('0.00')
        
        elif category == 'urgent_care':
            if plan_name == 'HDHP 3400':
                # 0% after deductible
                remaining_deductible = family_deductible - deductible_used[member]
                if remaining_deductible > 0:
                    applied_to_deductible = min(claim_total, remaining_deductible)
                    deductible_used[member] += applied_to_deductible
                    cost = applied_to_deductible
                else:
                    cost = Decimal('0.00')
            elif plan_name == 'OAP 750':
                # $50 copay, deductible waived
                cost = Decimal('50.00')
            else:  # OAP 250
                # $25 copay, deductible waived
                cost = Decimal('25.00')
        
        else:  # Other medical (primary care, specialist, etc.)
            # Estimate based on claim patterns
            # Primary care/specialist visits
            if claim_total < 300:  # Likely a visit
                if plan_name == 'HDHP 3400':
                    # $0 copay + 0% after deductible
                    remaining_deductible = family_deductible - deductible_used[member]
                    if remaining_deductible > 0:
                        applied_to_deductible = min(claim_total, remaining_deductible)
                        deductible_used[member] += applied_to_deductible
                        cost = applied_to_deductible
                    else:
                        cost = Decimal('0.00')
                elif plan_name == 'OAP 750':
                    # $25 copay, deductible waived
                    cost = Decimal('25.00')
                else:  # OAP 250
                    # $20 copay, deductible waived
                    cost = Decimal('20.00')
            else:
                # Larger medical services
                if plan_name == 'HDHP 3400':
                    # 0% after deductible
                    remaining_deductible = family_deductible - deductible_used[member]
                    if remaining_deductible > 0:
                        applied_to_deductible = min(claim_total, remaining_deductible)
                        deductible_used[member] += applied_to_deductible
                        cost = applied_to_deductible
                    else:
                        cost = Decimal('0.00')
                elif plan_name == 'OAP 750':
                    # 20% coinsurance after deductible
                    remaining_deductible = family_deductible - deductible_used[member]
                    if remaining_deductible > 0:
                        applied_to_deductible = min(claim_total, remaining_deductible)
                        deductible_used[member] += applied_to_deductible
                        remaining_after_deductible = claim_total - applied_to_deductible
                        cost = applied_to_deductible + (remaining_after_deductible * Decimal('0.20'))
                    else:
                        cost = claim_total * Decimal('0.20')
                else:  # OAP 250
                    # 10% coinsurance after deductible
                    remaining_deductible = family_deductible - deductible_used[member]
                    if remaining_deductible > 0:
                        applied_to_deductible = min(claim_total, remaining_deductible)
                        deductible_used[member] += applied_to_deductible
                        remaining_after_deductible = claim_total - applied_to_deductible
                        cost = applied_to_deductible + (remaining_after_deductible * Decimal('0.10'))
                    else:
                        cost = claim_total * Decimal('0.10')
        
        # Cap at out-of-pocket maximum
        total_oop += cost
        costs_by_category[category] += cost
    
    # Apply family out-of-pocket maximum
    total_oop = min(total_oop, family_oop_max)
    
    return {
        'annual_premium': annual_premium,
        'deductible_paid': min(sum(deductible_used.values()), family_deductible),
        'out_of_pocket': total_oop,
        'total_cost': annual_premium + total_oop,
        'costs_by_category': dict(costs_by_category)
    }

def main():
    # Plan details
    plans = {
        'HDHP 3400': {
            'monthly_premium': Decimal('74.41'),
            'family_deductible': Decimal('6800.00'),
            'individual_deductible': Decimal('3400.00'),
            'family_oop_max': Decimal('10000.00'),
        },
        'OAP 750': {
            'monthly_premium': Decimal('142.50'),
            'family_deductible': Decimal('2250.00'),
            'individual_deductible': Decimal('750.00'),
            'family_oop_max': Decimal('8000.00'),
        },
        'OAP 250': {
            'monthly_premium': Decimal('200.00'),
            'family_deductible': Decimal('750.00'),
            'individual_deductible': Decimal('250.00'),
            'family_oop_max': Decimal('4500.00'),
        }
    }
    
    # Read claims data
    claims = []
    with open('/Users/brentgroom/Projects/Personal-Finance/cognite-healthcare/ClaimDetail2025-12-11.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            claims.append(row)
    
    # Calculate actual costs paid in 2025
    actual_total_paid = sum(parse_currency(row.get('Your Responsibility', '0')) for row in claims)
    actual_claim_total = sum(parse_currency(row.get('Claim Total', '0')) for row in claims)
    
    print("=" * 80)
    print("2025 YTD CLAIMS ANALYSIS")
    print("=" * 80)
    print(f"\nTotal Claims Value: ${actual_claim_total:,.2f}")
    print(f"Actual Amount Paid (Your Responsibility): ${actual_total_paid:,.2f}")
    print(f"Number of Claims: {len(claims)}")
    
    # Count by type
    by_type = defaultdict(int)
    by_member = defaultdict(int)
    for row in claims:
        claim_type = row.get('Type of Claim', '').strip()
        member = row.get('Member Name', '').strip()
        if claim_type:
            by_type[claim_type] += 1
        if member:
            by_member[member] += 1
    
    print(f"\nClaims by Type:")
    for claim_type, count in by_type.items():
        print(f"  {claim_type}: {count}")
    
    print(f"\nClaims by Member:")
    for member, count in by_member.items():
        print(f"  {member}: {count}")
    
    print("\n" + "=" * 80)
    print("ESTIMATED ANNUAL COSTS FOR EACH PLAN")
    print("=" * 80)
    print("\nNote: This analysis is based on your 2025 YTD claims and estimates")
    print("what your costs would have been under each plan. Actual costs may vary.")
    print("\n" + "-" * 80)
    
    results = {}
    for plan_name, plan_details in plans.items():
        results[plan_name] = calculate_plan_costs(claims, plan_name, plan_details)
    
    # Sort by total cost
    sorted_plans = sorted(results.items(), key=lambda x: x[1]['total_cost'])
    
    for i, (plan_name, costs) in enumerate(sorted_plans, 1):
        print(f"\n{i}. {plan_name}")
        print(f"   Annual Premium:        ${costs['annual_premium']:,.2f}")
        print(f"   Deductible Paid:       ${costs['deductible_paid']:,.2f}")
        print(f"   Out-of-Pocket Costs:   ${costs['out_of_pocket']:,.2f}")
        print(f"   TOTAL ANNUAL COST:     ${costs['total_cost']:,.2f}")
    
    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    
    best_plan = sorted_plans[0][0]
    best_cost = sorted_plans[0][1]['total_cost']
    savings_vs_worst = sorted_plans[-1][1]['total_cost'] - best_cost
    
    print(f"\nBased on your 2025 YTD usage patterns:")
    print(f"  RECOMMENDED PLAN: {best_plan}")
    print(f"  Estimated Annual Cost: ${best_cost:,.2f}")
    print(f"  Potential Savings vs Most Expensive: ${savings_vs_worst:,.2f}")
    
    print("\n" + "-" * 80)
    print("IMPORTANT CONSIDERATIONS:")
    print("-" * 80)
    print("1. This analysis is based on partial year data (2025 YTD)")
    print("2. Your actual costs depend on:")
    print("   - Whether providers are in-network")
    print("   - Prescription drug tiers")
    print("   - Future medical needs")
    print("3. HDHP 3400 offers HSA eligibility (tax benefits)")
    print("4. OAP plans have lower deductibles but higher premiums")
    print("5. Consider your family's expected medical needs for 2026")

if __name__ == '__main__':
    main()

