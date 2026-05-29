from api.models import SuspiciousActivity

class AntiFraudService:

    @classmethod
    def check_multicuenta_ip(cls, login_logs, max_accounts=2, ip_address=None):
        """
        Regla 1: Misma IP con N cuentas distintas.
        Recibe una lista de tuplas o diccionarios con (user_id, ip) recientes.
        Si la cantidad de usuarios únicos para esa IP supera 'max_accounts', dispara alerta.
        """
        if not ip_address:
            return False

        # Filtramos los usuarios únicos que usaron esa misma IP
        unique_users = set([user_id for user_id, ip in login_logs if ip == ip_address])

        if len(unique_users) > max_accounts:
            # Creamos la alerta en la base de datos
            SuspiciousActivity.objects.create(
                rule_triggered='MULTIPLE_ACCOUNTS_SAME_IP',
                severity='HIGH',
                details={
                    'ip_address': ip_address,
                    'accounts_detected_count': len(unique_users),
                    'user_ids_involved': list(unique_users),
                    'threshold_limit': max_accounts
                }
            )
            return True
        return False

    @classmethod
    def check_identical_bets(cls, bets_list):
        """
        Regla 2: Patrones de apuestas idénticas en grupo (Colusión).
        Recibe una lista de apuestas hechas en un rango muy corto de tiempo.
        Si comparten mercado, selección, cuota y monto exacto por diferentes usuarios, es sospechoso.
        """
        if len(bets_list) < 2:
            return False

        # Tomamos la primera apuesta como base de comparación
        base_bet = bets_list[0]
        user_ids = [base_bet['user_id']]
        
        # Verificamos si las demás apuestas del bloque son copias idénticas en espejo
        for bet in bets_list[1:]:
            if (bet['market_id'] == base_bet['market_id'] and 
                bet['selection'] == base_bet['selection'] and 
                bet['odds'] == base_bet['odds'] and 
                bet['stake'] == base_bet['stake']):
                
                if bet['user_id'] not in user_ids:
                    user_ids.append(bet['user_id'])

        # Si hay más de un usuario involucrado en este patrón idéntico de apuestas
        if len(user_ids) >= 2:
            SuspiciousActivity.objects.create(
                rule_triggered='IDENTICAL_GROUP_BETTING',
                severity='MEDIUM',
                details={
                    'market_id': base_bet['market_id'],
                    'selection': base_bet['selection'],
                    'odds': base_bet['odds'],
                    'stake': base_bet['stake'],
                    'users_involved_count': len(user_ids),
                    'user_ids_involved': user_ids
                }
            )
            return True
        return False

    @classmethod
    def check_immediate_cashout(cls, tx_history):
        """
        Regla 3: Depósitos inmediatos seguidos de cash-out (Simulación para lavado).
        Recibe un diccionario analítico de transacciones recientes del usuario.
        """
        minutes = tx_history.get('minutes_elapsed', 99)
        deposit = tx_history.get('deposit_amount', 0.0)
        cashout = tx_history.get('cashout_amount', 0.0)
        wagered = tx_history.get('total_wagered', 0.0)
        user_id = tx_history.get('user_id')

        # Umbrales: Cashout en menos de 10 min de haber depositado, 
        # y habiendo arriesgado/apostado menos del 20% del valor depositado.
        if minutes <= 10 and deposit > 0:
            pct_wagered = (wagered / deposit) * 100
            
            if pct_wagered < 20.0:
                SuspiciousActivity.objects.create(
                    user_id=user_id,
                    rule_triggered='IMMEDIATE_DEPOSIT_CASHOUT',
                    severity='HIGH',
                    details={
                        'deposit_amount': deposit,
                        'cashout_amount': cashout,
                        'minutes_since_deposit': minutes,
                        'total_wagered_amount': wagered,
                        'percentage_wagered': f"{pct_wagered:.2f}%"
                    }
                )
                return True
        return False