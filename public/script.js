document.addEventListener('DOMContentLoaded', () => {
    const timestampEl = document.getElementById('timestamp');
    const dataTable = document.getElementById('data-table');
    const copyJsonBtn = document.getElementById('copy-json-btn');
    const configBtn = document.getElementById('config-btn');
    const configModal = document.getElementById('config-modal');
    const closeModalBtn = document.getElementById('close-modal-btn');
    const cancelBtn = document.getElementById('cancel-btn');
    const saveChangesBtn = document.getElementById('save-changes-btn');
    const watchlistInput = document.getElementById('watchlist-input');
    const marketInput = document.getElementById('market-input');
    const volatilityInput = document.getElementById('volatility-input');
    const bondsInput = document.getElementById('bonds-input');
    const dollarInput = document.getElementById('dollar-input');
    const loadingEl = document.getElementById('loading');
    const dataContainerEl = document.getElementById('data-container');
    const updateTimerEl = document.getElementById('update-timer');

    const marketStatusCard = document.getElementById('market-status-card');
    const marketStatusEl = document.getElementById('market-status');

    // Summary card elements
    const bondYieldsStatusEl = document.getElementById('bond-yields-status');
    const bondYieldsTagEl = document.getElementById('bond-yields-tag');
    const bondYieldsValueEl = document.getElementById('bond-yields-value');
    const usDollarValueEl = document.getElementById('us-dollar-value');
    const usDollarTagEl = document.getElementById('us-dollar-tag');
    const marketFearStatusEl = document.getElementById('market-fear-status');
    const marketFearTagEl = document.getElementById('market-fear-tag');
    const marketFearValueEl = document.getElementById('market-fear-value');

    let jsonData = {};
    let currentTickers = [];
    let countdownInterval;

    const INVERSE_MACRO = ['VXX', 'UUP'];
    const REFRESH_INTERVAL = 30; // seconds

    const fetchData = async () => {
        try {
            const isFirstLoad = !dataContainerEl.classList.contains('loaded');

            if (isFirstLoad) {
                loadingEl.classList.remove('hidden');
                dataContainerEl.classList.add('hidden');
            }

            const response = await fetch('/data');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            jsonData = await response.json();
            updateUI(jsonData);

            if (isFirstLoad) {
                loadingEl.classList.add('hidden');
                dataContainerEl.classList.remove('hidden');
                dataContainerEl.classList.add('loaded');
            }
            
            startUpdateTimer();

        } catch (error) {
            console.error("Failed to fetch data:", error);
            loadingEl.classList.remove('hidden');
            dataContainerEl.innerHTML = `<p class="text-center text-red-400">Error loading data. Check the console for details.</p>`;
        }
    };

    const updateUI = (data) => {
        timestampEl.textContent = data.timestamp;

        // Update market status
        marketStatusEl.textContent = data.status;
        marketStatusCard.className = `px-2 py-1 rounded text-white text-sm font-bold status-${data.status.toLowerCase().replace('_', '-')}`;


        // Update summary cards
        const bondYields = data.summary?.bond_yields;
        if (bondYields) {
            bondYieldsStatusEl.textContent = bondYields.status;
            bondYieldsTagEl.textContent = bondYields.tag;
            bondYieldsValueEl.textContent = bondYields.value;
        }

        const usDollar = data.summary?.us_dollar;
        if(usDollar) {
            usDollarValueEl.textContent = usDollar.value;
            usDollarTagEl.textContent = usDollar.tag;
        }

        const marketFear = data.summary?.market_fear;
        if(marketFear) {
            marketFearStatusEl.textContent = marketFear.status;
            marketFearTagEl.textContent = marketFear.tag;
            marketFearValueEl.textContent = marketFear.value;
        }

        const incomingTickers = new Set(data.tickers?.map(t => t.ticker) ?? []);
        
        // Remove old tickers
        for (const ticker of currentTickers) {
            if (!incomingTickers.has(ticker)) {
                const rowToRemove = document.getElementById(`ticker-row-${ticker}`);
                if (rowToRemove) {
                    rowToRemove.remove();
                }
            }
        }

        // Update or add new tickers
        data.tickers?.forEach(ticker => {
            const existingRow = document.getElementById(`ticker-row-${ticker.ticker}`);
            if (existingRow) {
                // Update existing row
                updateRow(existingRow, ticker);
            } else {
                // Add new row
                const newRow = createRow(ticker);
                dataTable.appendChild(newRow);
            }
        });
        
        currentTickers = Array.from(incomingTickers);
    };

    const createRow = (ticker) => {
        const row = document.createElement('tr');
        row.id = `ticker-row-${ticker.ticker}`;
        updateRow(row, ticker);
        return row;
    };
    
    const updateRow = (row, ticker) => {
        const formatCell = (value, prefix = '', decimals = 2, cssClass = '') => {
            const num = parseFloat(value);
            let content = isNaN(num) ? '-' : `${prefix}${num.toFixed(decimals)}`;
            let colorClass = num > 0 ? 'positive' : num < 0 ? 'negative' : '';
            return `<td class="py-2 px-4 text-right ${colorClass} ${cssClass}">${content}</td>`;
        };
        
        const formatTrend = (trend) => {
            const trendClass = `trend-${trend.toLowerCase()}`;
            return `<span class="${trendClass}">${trend}</span>`;
        }
        
        const formatScore = (ticker) => {
            const { score, ticker: symbol } = ticker;

            if (INVERSE_MACRO.includes(symbol)) {
                if (score <= -2) return `<span class="score-safe">${score} (SAFE)</span>`;
                if (score >= 2) return `<span class="score-risk">+${score} (RISK)</span>`;
            } else {
                if (score >= 3) return `<span class="score-bull">+${score} (BULL)</span>`;
                if (score <= -3) return `<span class="score-bear">${score} (BEAR)</span>`;
            }
            return `<span class="score-neutral">${score > 0 ? '+' : ''}${score}</span>`;
        }

        const vwapColorClass = ticker.price >= ticker.vwap ? 'positive' : 'negative';

        row.innerHTML = `
            <td class="py-2 px-4 font-bold text-left">${ticker.ticker}</td>
            ${formatCell(ticker.price, '', 2)}
            ${formatCell(ticker.gap_percent, '', 2)}
            <td class="py-2 px-4 text-right">${(ticker.volume / 1_000_000).toFixed(2)}M</td>
            ${formatCell(ticker.atr_percent, '', 2, 'hidden md:table-cell')}
            ${formatCell(ticker.rsi, '', 1, 'hidden md:table-cell')}
            <td class="py-2 px-4 text-right ${vwapColorClass}">${ticker.vwap.toFixed(2)}</td>
            <td class="py-2 px-4 text-center">${formatTrend(ticker.trend)}</td>
            <td class="py-2 px-4 text-center">${formatScore(ticker)}</td>
        `;
    };

    const startUpdateTimer = () => {
        clearInterval(countdownInterval);
        let countdown = REFRESH_INTERVAL;
        updateTimerEl.textContent = `Update in ${countdown}s`;

        countdownInterval = setInterval(() => {
            countdown--;
            updateTimerEl.textContent = `Update in ${countdown}s`;
            if (countdown <= 0) {
                clearInterval(countdownInterval);
                fetchData();
            }
        }, 1000);
    };

    configBtn.addEventListener('click', () => {
        // This assumes the config is fetched or available somewhere
        // For now, using placeholders or current values
        marketInput.value = jsonData.config?.market || 'SPY';
        volatilityInput.value = jsonData.config?.volatility || 'VXX';
        bondsInput.value = jsonData.config?.bonds || 'IEF';
        dollarInput.value = jsonData.config?.dollar || 'UUP';
        watchlistInput.value = currentTickers.join('\n');
        configModal.classList.remove('hidden');
    });

    closeModalBtn.addEventListener('click', () => {
        configModal.classList.add('hidden');
    });

    cancelBtn.addEventListener('click', () => {
        configModal.classList.add('hidden');
    });

    saveChangesBtn.addEventListener('click', async () => {
        const symbols = watchlistInput.value.split('\n').map(s => s.trim().toUpperCase()).filter(Boolean);
        const config = {
            market: marketInput.value.trim().toUpperCase(),
            volatility: volatilityInput.value.trim().toUpperCase(),
            bonds: bondsInput.value.trim().toUpperCase(),
            dollar: dollarInput.value.trim().toUpperCase(),
        };

        // Here you would likely have two separate API calls
        // For now, we assume one endpoint for watchlist and one for config
        
        try {
            // Update watchlist
            await fetch('/symbols', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(symbols),
            });

            // Update config (hypothetical endpoint)
            await fetch('/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config),
            });
            
            configModal.classList.add('hidden');
            await fetchData();

        } catch (error) {
            console.error("Error updating settings:", error);
        }
    });

    copyJsonBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(JSON.stringify(jsonData, null, 2))
            .then(() => alert("JSON copied to clipboard!"))
            .catch(err => console.error("Failed to copy JSON:", err));
    });
    
    // Add keyboard shortcut for copying JSON
    document.addEventListener('keydown', (e) => {
        if (e.key === 'c' || e.key === 'C') {
            // a check to prevent copying while typing in inputs
            if (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA') {
                return;
            }
            copyJsonBtn.click();
        }
    });

    fetchData();
});