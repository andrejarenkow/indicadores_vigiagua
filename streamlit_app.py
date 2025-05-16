import streamlit as st
import pandas as pd
import numpy as np
import glob
from io import BytesIO
import zipfile

# Configuração da página
st.set_page_config(page_title="Análise de Amostras de Água", layout="wide")

# Título do aplicativo
st.title("Painel de Análise de Amostras de Água")

# Sidebar para upload e configurações
with st.sidebar:
    st.header("Configurações")
    
    # Upload do arquivo
    uploaded_file = st.file_uploader("Carregar arquivo ZIP com dados", type="zip")
    
    # Seleção do mês limite
    mes_limite = st.slider("Mês limite para análise", 1, 12, 4)
    
    # Motivos de coleta
    motivos_coleta = st.multiselect(
        "Motivos da Coleta a considerar",
        options=['Potabilidade', 'Desastre', 'Outros'],
        default=['Potabilidade', 'Desastre']
    )

# Função para processar os dados
def processar_dados(arquivo_zip, mes_limite, motivos_coleta):
    # Lê o arquivo CSV do ZIP
    with zipfile.ZipFile(arquivo_zip) as z:
        # Assume que há apenas um arquivo CSV no ZIP
        csv_filename = [f for f in z.namelist() if f.endswith('.csv')][0]
        with z.open(csv_filename) as f:
            dados = pd.read_csv(f, sep=';', encoding='latin1')
    
    # Processamento dos dados
    dados = dados.drop_duplicates('Solicitação')
    dados = dados[dados['Motivo da Coleta'].isin(motivos_coleta)].reset_index(drop=True)
    
    # Criar uma coluna do mês
    dados['Mês'] = pd.to_datetime(dados['Data de Coleta']).dt.month
    
    # Filtro até o mês limite
    dados = dados[dados['Mês'] <= mes_limite]
    
    # Correção de nome
    dados['Municipio do Solicitante'] = dados['Municipio do Solicitante'].replace(
        "SANT'' ANA DO LIVRAMENTO", "SANT'ANA DO LIVRAMENTO"
    )
    
    return dados

# Carregar dados mínimos por município
@st.cache_data
def carregar_dados_minimos():
    url = 'https://github.com/andrejarenkow/csv/raw/refs/heads/master/Amostras%20minimas%20por%20municipio.xlsx'
    dados_minimos = pd.read_excel(url)
    dados_minimos = dados_minimos[['Município', 'Mensal']].reset_index(drop=True)
    dados_minimos = dados_minimos[dados_minimos['Município'] != 'TOTAL']
    return dados_minimos

# Se um arquivo foi carregado
if uploaded_file is not None:
    try:
        # Processar dados
        dados = processar_dados(uploaded_file, mes_limite, motivos_coleta)
        dados_minimos_por_municipio = carregar_dados_minimos()
        
        # Tabela dinâmica de análises por município
        tabela_dinamica = pd.pivot_table(
            dados, 
            index='Municipio do Solicitante', 
            aggfunc='size'
        ).reset_index().rename(columns={
            0: 'Amostras_coletadas',
            'Municipio do Solicitante': 'Município'
        })
        
        tabela_dinamica = tabela_dinamica.merge(
            dados_minimos_por_municipio, 
            on='Município', 
            how='right'
        ).fillna(0)
        
        # Criar colunas para indicadores
        tabela_dinamica['Amostras_minimo_ate_mes_limite'] = tabela_dinamica['Mensal'] * mes_limite
        tabela_dinamica['Indicador'] = tabela_dinamica['Amostras_coletadas'] / tabela_dinamica['Amostras_minimo_ate_mes_limite']
        
        # Calcular métricas
        valor_indicador = round(tabela_dinamica[tabela_dinamica['Indicador'] >= 0.9].shape[0] / 497 * 100, 2)
        municipios_zerados = len(tabela_dinamica[tabela_dinamica['Amostras_coletadas'] == 0])
        
        # Exibir métricas
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Municípios com indicador ≥ 90%", f"{valor_indicador}%")
        with col2:
            st.metric("Municípios sem amostras coletadas", municipios_zerados)
        
        # Tabela pivot por mês
        st.subheader("Amostras por Município e Mês")
        tabela_pivot = dados.pivot_table(
            index='Municipio do Solicitante',
            columns='Mês',
            values='Solicitação',
            aggfunc='count',
            fill_value=0
        )
        st.dataframe(tabela_pivot)
        
        # Tabela completa com status
        st.subheader("Análise Completa por Município")
        tabela_completa = tabela_pivot.merge(
            dados_minimos_por_municipio,
            left_on='Municipio do Solicitante',
            right_on='Município',
            how='right'
        )
        
        # Garantir colunas de meses
        meses = tabela_pivot.columns.tolist()
        for mes in meses:
            coluna = str(mes)
            if coluna not in tabela_completa.columns:
                tabela_completa[coluna] = 0
        
        # Calcular total e status
        tabela_completa['Total de Amostras'] = tabela_completa[[str(mes) for mes in meses]].sum(axis=1)
        
        def verificar_status(row, meses, min_amostras):
            total_coletadas = row['Total de Amostras']
            total_min_exigido = row['Mensal'] * len(meses)
            atingiu_anual = total_coletadas >= total_min_exigido
            atingiu_mensal = all(row[str(mes)] >= 0.80 * row['Mensal'] for mes in meses)
            return "Atendeu" if atingiu_anual else "Não Atendeu"
        
        tabela_completa['Status'] = tabela_completa.apply(
            lambda row: verificar_status(row, meses, row['Mensal']),
            axis=1
        )
        
        # Reorganizar colunas
        colunas_primeiro = ['Município', 'Mensal']
        colunas_numericas = sorted(
            [col for col in tabela_completa.columns if str(col).isdigit()],
            key=lambda x: int(x)
        colunas_demais = [col for col in tabela_completa.columns if not str(col).isdigit() and col not in colunas_primeiro]
        tabela_completa = tabela_completa[colunas_primeiro + colunas_numericas + colunas_demais]
        
        # Exibir tabela
        st.dataframe(tabela_completa)
        
        # Resumo por status
        st.subheader("Resumo por Status")
        st.table(tabela_completa['Status'].value_counts().reset_index().rename(
            columns={'index': 'Status', 'Status': 'Quantidade'}))
        
        # Municípios sem amostras
        st.subheader("Municípios sem Amostras Coletadas")
        st.dataframe(tabela_dinamica[tabela_dinamica['Amostras_coletadas'] == 0])
        
    except Exception as e:
        st.error(f"Ocorreu um erro ao processar o arquivo: {str(e)}")
else:
    st.info("Por favor, carregue um arquivo ZIP para iniciar a análise.")

# Instruções
with st.expander("Instruções de Uso"):
    st.markdown("""
    1. **Carregar arquivo**: No menu lateral, clique em "Browse files" e selecione o arquivo ZIP com os dados.
    2. **Configurações**: Ajuste o mês limite e os motivos de coleta conforme necessário.
    3. **Visualização**: O painel exibirá automaticamente as análises após o carregamento do arquivo.
    
    **Observações**:
    - O arquivo ZIP deve conter um arquivo CSV com os dados de amostras.
    - Os dados mínimos por município são carregados automaticamente do GitHub.
    """)
